"""
QAOA solvers for Q-Flow, built directly on Qiskit primitives.

Modes
-----
qaoa_ideal  Exact statevector during parameter optimisation, then shot sampling
            on a noiseless AerSimulator.
qaoa_noisy  Same circuit on AerSimulator with a noise model. Two models:
              "depolarizing"  tunable gate and readout error, all to all
                              connectivity (isolates the effect of noise level)
              "fake_backend"  calibration data and qubit connectivity of a real
                              IBM device (adds routing SWAPs, so it is realistic)
            Parameters are optimised on the ideal statevector and transferred,
            exactly as they would be for real hardware. Fine tuning under noise
            (optimise_under_noise=True) is available but in testing cost about
            10x the runtime for no measurable gain.

Methodology notes
-----------------
* The circuit is built from the same QUBO every classical solver uses, so all
  modes optimise an identical cost function.
* Hamiltonian coefficients are normalised by their largest magnitude, so the
  gamma range is comparable across problems of different scale.
* p = 1 parameters come from a coarse grid then COBYLA. Each deeper p is warm
  started from the previous optimum by linear interpolation (INTERP, Zhou et al.
  2020), which avoids the random restarts that make deep QAOA unreliable.
* Bit order: Qiskit is little endian, so statevector index k and the integer
  value of a counts key both encode x_i = (k >> i) & 1, exactly the convention
  used by RoutingProblem.all_energies(). No manual string reversal is needed.
* With few qubits, shot sampling alone will often stumble on the optimum. The
  headline metrics are therefore probability of the optimum and mean
  approximation ratio, always shown next to a uniform random baseline.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict, field

import numpy as np
from scipy.optimize import minimize
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import ParameterVector
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

from app.core.problem import RoutingProblem
from app.core.solvers.base import SolverResult
from app.core.solvers.exact import solve_exact

# Baseline error rates for noise_level = 1.0, roughly in line with current
# superconducting devices. Experiment 2 scales these up and down.
BASE_P1 = 1e-3      # single qubit gate depolarising probability
BASE_P2 = 1e-2      # two qubit gate depolarising probability
BASE_READOUT = 2e-2  # measurement bit flip probability


@dataclass
class QAOAConfig:
    reps: int = 1                         # QAOA depth p
    shots: int = 4096
    maxiter: int = 200
    seed: int = 7
    noise: str | None = None              # None, "depolarizing", "fake_backend"
    noise_level: float = 1.0              # multiplier on BASE_* (depolarizing only)
    fake_backend: str = "FakeTorino"
    optimise_under_noise: bool = False    # default: transfer ideal parameters (as on hardware)
    noisy_maxiter: int = 60
    grid_points: int = 16                 # per axis, for the p = 1 grid search


# ====================================================================== Ising
def qubo_to_ising(problem: RoutingProblem) -> tuple[dict[int, float], dict[tuple[int, int], float], float]:
    """x_i = (1 - Z_i) / 2  ->  E = const + sum h_i Z_i + sum J_ij Z_i Z_j."""
    h: dict[int, float] = {i: 0.0 for i in range(problem.num_variables)}
    J: dict[tuple[int, int], float] = {}
    const = problem.offset
    for i, c in problem.linear.items():
        const += c / 2
        h[i] -= c / 2
    for (i, j), c in problem.quadratic.items():
        const += c / 4
        h[i] -= c / 4
        h[j] -= c / 4
        key = (min(i, j), max(i, j))
        J[key] = J.get(key, 0.0) + c / 4
    return h, J, const


def build_qaoa_circuit(problem: RoutingProblem, reps: int, measure: bool = True):
    h, J, _ = qubo_to_ising(problem)
    scale = max([abs(v) for v in h.values()] + [abs(v) for v in J.values()] + [1e-12])
    n = problem.num_variables
    gammas = ParameterVector("gamma", reps)
    betas = ParameterVector("beta", reps)
    qc = QuantumCircuit(n, name=f"QAOA_p{reps}")
    qc.h(range(n))
    for layer in range(reps):
        g, b = gammas[layer], betas[layer]
        for (i, j), c in J.items():
            if c:
                qc.rzz(2 * g * c / scale, i, j)
        for i, c in h.items():
            if c:
                qc.rz(2 * g * c / scale, i)
        qc.rx(2 * b, range(n))
    if measure:
        qc.measure_all()
    return qc, list(gammas) + list(betas)


# ================================================================ metrics
def analyse_distribution(problem: RoutingProblem, probs: np.ndarray, shots: int | None,
                         reference: SolverResult) -> dict:
    """
    Shared metrics for any output distribution (ideal, noisy or hardware).
    `probs[k]` is the probability of bitstring index k (little endian).
    """
    energies = problem.all_energies()
    n = problem.num_variables
    ks = np.arange(2 ** n)
    X = ((ks[:, None] >> np.arange(n)) & 1)
    feasible = np.all([X[:, idxs].sum(axis=1) == 1 for idxs in problem.group_options.values()], axis=0)

    e_opt = reference.extra["optimal_energy"]
    e_worst = reference.extra["worst_feasible_energy"]
    span = (e_worst - e_opt) or 1.0
    optimal = np.isclose(energies, e_opt, atol=1e-9) & feasible
    ratio = np.where(feasible, np.clip((e_worst - energies) / span, 0, 1), 0.0)

    support = np.nonzero(probs > 0)[0]
    best_k = int(support[np.argmin(energies[support])])
    likely_k = int(np.argmax(probs))
    top = support[np.argsort(-probs[support])][:10]

    def bits(k):
        return [int(b) for b in X[k]]

    return {
        "shots": shots,
        "expected_energy": float(probs @ energies),
        "prob_optimal": float(probs[optimal].sum()),
        "prob_feasible": float(probs[feasible].sum()),
        "mean_approx_ratio": float(probs @ ratio),
        "best_sampled": {"bitstring": bits(best_k), "energy": float(energies[best_k]),
                         "approx_ratio": float(ratio[best_k]), "is_optimal": bool(optimal[best_k])},
        "most_likely": {"bitstring": bits(likely_k), "probability": float(probs[likely_k]),
                        "approx_ratio": float(ratio[likely_k]), "is_optimal": bool(optimal[likely_k]),
                        "feasible": bool(feasible[likely_k])},
        "random_baseline": {
            "prob_optimal": float(optimal.mean()),
            "prob_feasible": float(feasible.mean()),
            "mean_approx_ratio": float(ratio.mean()),
        },
        "top_bitstrings": [
            {"bitstring": bits(int(k)), "probability": float(probs[k]), "energy": float(energies[k]),
             "feasible": bool(feasible[k]), "is_optimal": bool(optimal[k])}
            for k in top
        ],
    }


def counts_to_probs(counts: dict[str, int], n: int) -> np.ndarray:
    probs = np.zeros(2 ** n)
    total = sum(counts.values())
    for key, c in counts.items():
        probs[int(key.replace(" ", ""), 2)] += c / total
    return probs


# =========================================================== noise models
def depolarizing_noise_model(level: float) -> NoiseModel:
    nm = NoiseModel(basis_gates=["rz", "sx", "x", "cx"])
    if level <= 0:
        return nm
    p1, p2, pr = min(BASE_P1 * level, 0.75), min(BASE_P2 * level, 0.9375), min(BASE_READOUT * level, 0.5)
    nm.add_all_qubit_quantum_error(depolarizing_error(p1, 1), ["sx", "x"])
    nm.add_all_qubit_quantum_error(depolarizing_error(p2, 2), ["cx"])
    nm.add_all_qubit_readout_error(ReadoutError([[1 - pr, pr], [pr, 1 - pr]]))
    return nm


def make_simulator(cfg: QAOAConfig):
    """Returns (simulator, transpile kwargs, description)."""
    if cfg.noise is None:
        return AerSimulator(seed_simulator=cfg.seed), {"basis_gates": ["rz", "sx", "x", "cx"]}, "ideal"
    if cfg.noise == "depolarizing":
        nm = depolarizing_noise_model(cfg.noise_level)
        sim = AerSimulator(noise_model=nm, seed_simulator=cfg.seed)
        return sim, {"basis_gates": nm.basis_gates}, f"depolarizing x{cfg.noise_level:g}"
    if cfg.noise == "fake_backend":
        from qiskit_ibm_runtime import fake_provider
        if not hasattr(fake_provider, cfg.fake_backend):
            raise ValueError(f"Unknown fake backend '{cfg.fake_backend}'.")
        backend = getattr(fake_provider, cfg.fake_backend)()
        sim = AerSimulator.from_backend(backend, seed_simulator=cfg.seed)
        return sim, {"backend": backend}, f"{cfg.fake_backend} calibrated noise"
    raise ValueError(f"Unknown noise option '{cfg.noise}'.")


def circuit_stats(qc: QuantumCircuit) -> dict:
    ops = qc.count_ops()
    two_q = sum(1 for inst in qc.data if inst.operation.num_qubits == 2)
    return {"depth": qc.depth(), "two_qubit_gates": two_q, "total_gates": int(sum(ops.values()) - ops.get("measure", 0) - ops.get("barrier", 0))}


# ======================================================= ideal optimisation
class IdealOptimiser:
    """Exact expectation via statevector. Cheap enough for the 4 to 12 qubit range."""

    def __init__(self, problem: RoutingProblem, cfg: QAOAConfig):
        self.problem, self.cfg = problem, cfg
        self.energies = problem.all_energies()
        self.history: list[float] = []
        self._cache: dict = {}

    def expectation(self, reps: int, theta: np.ndarray) -> float:
        qc, params = self._circuit(reps)
        sv = Statevector(qc.assign_parameters(dict(zip(params, theta))))
        return float(sv.probabilities() @ self.energies)

    def probabilities(self, reps: int, theta: np.ndarray) -> np.ndarray:
        qc, params = self._circuit(reps)
        return Statevector(qc.assign_parameters(dict(zip(params, theta)))).probabilities()

    def _circuit(self, reps):
        if reps not in self._cache:
            self._cache[reps] = build_qaoa_circuit(self.problem, reps, measure=False)
        return self._cache[reps]

    def optimise(self, reps: int) -> tuple[np.ndarray, int]:
        theta, evals = self._optimise_p1()
        for p in range(2, reps + 1):
            theta, e = self._refine(p, interp(theta, p - 1))
            evals += e
        return theta, evals

    def _optimise_p1(self):
        m = self.cfg.grid_points
        best, best_theta = np.inf, None
        for g in np.linspace(0.05, np.pi, m):
            for b in np.linspace(0.05, np.pi / 2, m):
                v = self.expectation(1, np.array([g, b]))
                if v < best:
                    best, best_theta = v, np.array([g, b])
        theta, evals = self._refine(1, best_theta)
        return theta, evals + m * m

    def _refine(self, reps, theta0):
        def f(t):
            v = self.expectation(reps, t)
            self.history.append(v)
            return v
        res = minimize(f, theta0, method="COBYLA", options={"maxiter": self.cfg.maxiter, "rhobeg": 0.2})
        return np.asarray(res.x), int(res.nfev)


def interp(theta: np.ndarray, p: int) -> np.ndarray:
    """INTERP warm start: p layer optimum -> initial point for p + 1 layers."""
    gam, bet = theta[:p], theta[p:]

    def grow(v):
        out = np.zeros(p + 1)
        for i in range(p + 1):
            left = v[i - 1] if i - 1 >= 0 else 0.0
            right = v[i] if i < p else 0.0
            out[i] = (i / p) * left + ((p - i) / p) * right
        return out
    return np.concatenate([grow(gam), grow(bet)])


# ================================================================== runner
def optimise_parameters(problem: RoutingProblem, reps: int, cfg: QAOAConfig | None = None) -> dict:
    """Ideal parameter optimisation on its own, so experiments can reuse the result
    across many noise levels or backends without retraining."""
    cfg = cfg or QAOAConfig(reps=reps)
    t0 = time.perf_counter()
    ideal = IdealOptimiser(problem, cfg)
    theta, evals = ideal.optimise(reps)
    return {"theta": theta, "evaluations": evals, "history": list(ideal.history),
            "ideal_expected_energy": ideal.expectation(reps, theta),
            "optimise_time_s": time.perf_counter() - t0}


def run_qaoa(problem: RoutingProblem, cfg: QAOAConfig, solver_name: str,
             trained: dict | None = None, reference: SolverResult | None = None) -> SolverResult:
    """
    trained:   output of optimise_parameters for the same problem and reps; skips training.
    reference: output of solve_exact for the same problem; skips recomputing it.
    """
    if problem.num_qubits > 16:
        raise ValueError(f"{problem.num_qubits} qubits is beyond the QAOA simulation limit (16).")
    t0 = time.perf_counter()
    reference = reference or solve_exact(problem)
    n = problem.num_variables

    # 1. Optimise parameters on the ideal statevector (also the hardware transfer point).
    reused = trained is not None
    trained = trained or optimise_parameters(problem, cfg.reps, cfg)
    theta = np.asarray(trained["theta"])
    evals = trained["evaluations"]
    ideal_expectation = trained["ideal_expected_energy"]
    history = list(trained["history"])

    # 2. Build and transpile the measured circuit for the chosen simulator.
    sim, tkw, noise_desc = make_simulator(cfg)
    logical, params = build_qaoa_circuit(problem, cfg.reps, measure=True)
    compiled = transpile(logical, optimization_level=1, seed_transpiler=cfg.seed, **tkw)

    def sample(t, shots):
        bound = compiled.assign_parameters(dict(zip(params, t)))
        counts = sim.run(bound, shots=shots).result().get_counts()
        return counts_to_probs(counts, n)

    energies = problem.all_energies()

    # 3. Optional fine tuning under noise, warm started from the ideal optimum.
    noisy_evals = 0
    if cfg.noise and cfg.optimise_under_noise:
        def f(t):
            v = float(sample(t, max(cfg.shots // 4, 512)) @ energies)
            history.append(v)
            return v
        res = minimize(f, theta, method="COBYLA", options={"maxiter": cfg.noisy_maxiter, "rhobeg": 0.1})
        if res.fun < f(theta):
            theta = np.asarray(res.x)
        noisy_evals = int(res.nfev)

    # 4. Final sampling with the full shot budget.
    probs = sample(theta, cfg.shots)
    metrics = analyse_distribution(problem, probs, cfg.shots, reference)
    # Total cost of producing this answer always includes parameter training,
    # even when the trained parameters were computed once and reused.
    execution = time.perf_counter() - t0
    if reused:
        runtime = execution + trained["optimise_time_s"]
    else:
        runtime = execution

    best = metrics["best_sampled"]
    status = "optimal" if best["is_optimal"] else ("feasible" if problem.is_feasible(best["bitstring"]) else "infeasible")
    return SolverResult.build(
        problem, solver_name, status, best["bitstring"], runtime,
        metrics=metrics,
        config=asdict(cfg),
        noise_model=noise_desc,
        parameters={"gamma": theta[: cfg.reps].tolist(), "beta": theta[cfg.reps:].tolist()},
        ideal_expected_energy=ideal_expectation,
        optimal_energy=reference.extra["optimal_energy"],
        circuit={"qubits": n, "reps": cfg.reps, "logical": circuit_stats(logical),
                 "transpiled": circuit_stats(compiled)},
        evaluations={"ideal": evals, "noisy": noisy_evals},
        timing={"training_s": trained["optimise_time_s"], "total_s": runtime,
                "execution_s": runtime - trained["optimise_time_s"]},
        history=history,
    )


def solve_qaoa_ideal(problem: RoutingProblem, trained: dict | None = None,
                     reference: SolverResult | None = None, **kw) -> SolverResult:
    return run_qaoa(problem, QAOAConfig(noise=None, **kw), "qaoa_ideal", trained, reference)


def solve_qaoa_noisy(problem: RoutingProblem, noise: str = "depolarizing", trained: dict | None = None,
                     reference: SolverResult | None = None, **kw) -> SolverResult:
    return run_qaoa(problem, QAOAConfig(noise=noise, **kw), "qaoa_noisy", trained, reference)
