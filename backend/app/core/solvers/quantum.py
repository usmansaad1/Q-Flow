# WHAT THIS FILE IS FOR: the quantum method, called QAOA (Quantum Approximate Optimisation Algorithm).
# It runs on a simulated quantum computer, either perfect ("ideal") or with realistic errors ("noisy").
# Each possible route is one qubit: a quantum bit that is finally read as 0 (not taken) or 1 (taken).
# The experiments, the website and the real hardware runner all use the pieces in this file.
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

# Noise means the small random mistakes real quantum chips make.
# These are the chances of a mistake per step, used by the "noisy" simulator.
# Baseline error rates for noise_level = 1.0, roughly in line with current
# superconducting devices. Experiment 2 scales these up and down.
BASE_P1 = 1e-3      # single qubit gate depolarising probability
BASE_P2 = 1e-2      # two qubit gate depolarising probability
BASE_READOUT = 2e-2  # measurement bit flip probability


# All the settings for one quantum run, in one place.
# reps: how many cost and mixer layers to stack. shots: how many times the program is run and read.
# The rest choose the noise type and strength and how hard to search for good dial settings.
@dataclass
class QAOAConfig:
    reps: int = 1                         # QAOA depth p
    shots: int = 4096
    # The most tries the tuner may make when training the dials.
    maxiter: int = 200
    # A fixed starting number for the random parts, so the same run gives the same result every time.
    seed: int = 7
    noise: str | None = None              # None, "depolarizing", "fake_backend"
    noise_level: float = 1.0              # multiplier on BASE_* (depolarizing only)
    fake_backend: str = "FakeTorino"
    optimise_under_noise: bool = False    # default: transfer ideal parameters (as on hardware)
    noisy_maxiter: int = 60
    grid_points: int = 16                 # per axis, for the p = 1 grid search


# ====================================================================== Ising
# Rewrites the cost table into the form quantum gates work with.
# h says how much each route costs on its own; J says how much two routes cost together.
# The cost of every plan stays exactly the same; only the bookkeeping changes.
def qubo_to_ising(problem: RoutingProblem) -> tuple[dict[int, float], dict[tuple[int, int], float], float]:
    """x_i = (1 - Z_i) / 2  ->  E = const + sum h_i Z_i + sum J_ij Z_i Z_j."""
    # Start with no costs, then move each piece of the cost table across.
    h: dict[int, float] = {i: 0.0 for i in range(problem.num_variables)}
    J: dict[tuple[int, int], float] = {}
    const = problem.offset
    # Single route costs: half goes to the fixed constant, half (with a minus sign) to h.
    for i, c in problem.linear.items():
        const += c / 2
        h[i] -= c / 2
    # Pair costs: a quarter each to the constant, to each route's h, and to the pair's J.
    for (i, j), c in problem.quadratic.items():
        const += c / 4
        h[i] -= c / 4
        h[j] -= c / 4
        key = (min(i, j), max(i, j))
        J[key] = J.get(key, 0.0) + c / 4
    return h, J, const


# Builds the quantum program (a "circuit"). It has two dials per layer, gamma and beta.
# The dials are left blank here and filled in later, once training has found good values.
# Returns the circuit and the list of its dials.
def build_qaoa_circuit(problem: RoutingProblem, reps: int, measure: bool = True):
    # Shrink all costs so the largest is 1, so the same dial range suits any venue.
    h, J, _ = qubo_to_ising(problem)
    scale = max([abs(v) for v in h.values()] + [abs(v) for v in J.values()] + [1e-12])
    n = problem.num_variables
    gammas = ParameterVector("gamma", reps)
    betas = ParameterVector("beta", reps)
    qc = QuantumCircuit(n, name=f"QAOA_p{reps}")
    # The starting even mix: every qubit is put halfway between 0 and 1.
    # At this point every possible plan is equally likely, like shuffling a deck fairly.
    qc.h(range(n))
    for layer in range(reps):
        g, b = gammas[layer], betas[layer]
        # Cost gates: nudge each plan by an amount tied to its cost, scaled by gamma.
        # First the costs for pairs of routes, then the cost of each route alone.
        for (i, j), c in J.items():
            if c:
                qc.rzz(2 * g * c / scale, i, j)
        for i, c in h.items():
            if c:
                qc.rz(2 * g * c / scale, i)
        # Mixer gates: let probability flow between nearby plans, by an amount set by beta.
        # Together with the cost gates, this steers likelihood towards cheap plans.
        qc.rx(2 * b, range(n))
    # Reading the qubits at the end turns each into a plain 0 or 1, giving one plan.
    if measure:
        qc.measure_all()
    return qc, list(gammas) + list(betas)


# ================================================================ metrics
# Marks a quantum run. Takes the chance of each plan coming out and turns it into quality measures.
# Used for the perfect simulator, the noisy simulator and the real IBM machine alike.
# "reference" is the exact solver's answer key, giving the best and worst valid costs.
def analyse_distribution(problem: RoutingProblem, probs: np.ndarray, shots: int | None,
                         reference: SolverResult) -> dict:
    """
    Shared metrics for any output distribution (ideal, noisy or hardware).
    `probs[k]` is the probability of bitstring index k (little endian).
    """
    # Step 1: list every possible plan, its cost, and whether it is valid (one route per group).
    energies = problem.all_energies()
    n = problem.num_variables
    ks = np.arange(2 ** n)
    X = ((ks[:, None] >> np.arange(n)) & 1)
    feasible = np.all([X[:, idxs].sum(axis=1) == 1 for idxs in problem.group_options.values()], axis=0)

    # Step 2: give every plan a grade from 0 to 1 (the "approximation ratio").
    # 1 means as good as the best valid plan, 0 means as bad as the worst. Invalid plans get 0.
    e_opt = reference.extra["optimal_energy"]
    e_worst = reference.extra["worst_feasible_energy"]
    span = e_worst - e_opt
    optimal = np.isclose(energies, e_opt, atol=1e-9) & feasible
    if span > 1e-12:
        ratio = np.where(feasible, np.clip((e_worst - energies) / span, 0, 1), 0.0)
    else:
        # Only one valid plan exists, so every valid answer is the best one (100%).
        ratio = np.where(feasible, 1.0, 0.0)

    # Step 3: among plans that actually came up, find the cheapest, the most frequent and the top ten.
    support = np.nonzero(probs > 0)[0]
    best_k = int(support[np.argmin(energies[support])])
    likely_k = int(np.argmax(probs))
    top = support[np.argsort(-probs[support])][:10]

    # Turns a plan's index number back into its row of 0s and 1s.
    def bits(k):
        return [int(b) for b in X[k]]

    # Step 4: the report card.
    # expected_energy: the average cost of the plans that come out. Lower is better.
    # prob_optimal: the chance one run gives the very best plan.
    # prob_feasible: the chance one run gives a valid plan at all.
    # mean_approx_ratio: the average grade from 0 to 1 across all runs.
    # best_sampled: the best plan seen. most_likely: the plan that came up most often.
    # random_baseline: the same measures for blind guessing, to show what the quantum method adds.
    # top_bitstrings: the ten most common plans with their chance, cost and validity.
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


# Turns a tally of results (e.g. "this plan came up 300 times") into shares of the total.
# Each run of the program is a "shot"; more shots give a more reliable picture.
def counts_to_probs(counts: dict[str, int], n: int) -> np.ndarray:
    probs = np.zeros(2 ** n)
    total = sum(counts.values())
    for key, c in counts.items():
        probs[int(key.replace(" ", ""), 2)] += c / total
    return probs


# =========================================================== noise models
# Builds a simple, adjustable noise recipe for the simulator.
# Each gate has a small chance of scrambling its qubits, and each reading a chance of flipping 0 and 1.
# "level" multiplies the base chances; 0 means no noise, and very high values are capped.
def depolarizing_noise_model(level: float) -> NoiseModel:
    # The basic gates the simulator works in; every circuit is rewritten into these.
    nm = NoiseModel(basis_gates=["rz", "sx", "x", "cx"])
    if level <= 0:
        return nm
    # p1: one qubit gate error, p2: two qubit gate error, pr: reading error.
    p1, p2, pr = min(BASE_P1 * level, 0.75), min(BASE_P2 * level, 0.9375), min(BASE_READOUT * level, 0.5)
    nm.add_all_qubit_quantum_error(depolarizing_error(p1, 1), ["sx", "x"])
    nm.add_all_qubit_quantum_error(depolarizing_error(p2, 2), ["cx"])
    nm.add_all_qubit_readout_error(ReadoutError([[1 - pr, pr], [pr, 1 - pr]]))
    return nm


# Sets up the simulated quantum computer for this run: perfect, simple noise,
# or a copy of a real IBM chip's measured errors and wiring (a "fake backend").
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


# Measures the size of a quantum program: its depth (steps in sequence) and its gate counts.
# Gates that link two qubits are counted apart, since they are the main source of errors.
def circuit_stats(qc: QuantumCircuit) -> dict:
    ops = qc.count_ops()
    two_q = sum(1 for inst in qc.data if inst.operation.num_qubits == 2)
    return {"depth": qc.depth(), "two_qubit_gates": two_q, "total_gates": int(sum(ops.values()) - ops.get("measure", 0) - ops.get("barrier", 0))}


# ======================================================= ideal optimisation
# Trains the dials (gamma and beta angles) using perfect, noise free maths on this computer.
# It tries settings, works out the average plan cost for each, and keeps the lowest.
class IdealOptimiser:
    """Exact expectation via statevector. Cheap enough for the 4 to 12 qubit range."""

    # Stores the venue, the settings, the cost of every plan and a log of scores tried.
    def __init__(self, problem: RoutingProblem, cfg: QAOAConfig):
        self.problem, self.cfg = problem, cfg
        self.energies = problem.all_energies()
        self.history: list[float] = []
        self._cache: dict = {}

    # Average plan cost the program would give with these dial settings. Training lowers this.
    def expectation(self, reps: int, theta: np.ndarray) -> float:
        qc, params = self._circuit(reps)
        sv = Statevector(qc.assign_parameters(dict(zip(params, theta))))
        return float(sv.probabilities() @ self.energies)

    # The exact chance of each plan coming out with these dial settings.
    def probabilities(self, reps: int, theta: np.ndarray) -> np.ndarray:
        qc, params = self._circuit(reps)
        return Statevector(qc.assign_parameters(dict(zip(params, theta)))).probabilities()

    # Builds the program for a given number of layers once, then reuses it.
    def _circuit(self, reps):
        if reps not in self._cache:
            self._cache[reps] = build_qaoa_circuit(self.problem, reps, measure=False)
        return self._cache[reps]

    # Trains one layer first, then adds layers one at a time.
    # Each new layer starts from a stretched copy of the previous best settings.
    # Returns the final dial settings and how many settings were tried.
    def optimise(self, reps: int) -> tuple[np.ndarray, int]:
        theta, evals = self._optimise_p1()
        for p in range(2, reps + 1):
            theta, e = self._refine(p, interp(theta, p - 1))
            evals += e
        return theta, evals

    # For one layer: try a grid of gamma and beta values, take the best, then fine tune it.
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

    # Fine tunes the dials from a starting guess with COBYLA, a standard trial and error tuner.
    # Every score it tries is added to the history log for the charts.
    def _refine(self, reps, theta0):
        # The score the tuner tries to lower: average plan cost, logged each time.
        def f(t):
            v = self.expectation(reps, t)
            self.history.append(v)
            return v
        res = minimize(f, theta0, method="COBYLA", options={"maxiter": self.cfg.maxiter, "rhobeg": 0.2})
        return np.asarray(res.x), int(res.nfev)


# Stretches good settings for p layers into a starting guess for p + 1 layers.
# It blends neighbouring values smoothly, a published method known to work well.
def interp(theta: np.ndarray, p: int) -> np.ndarray:
    """INTERP warm start: p layer optimum -> initial point for p + 1 layers."""
    gam, bet = theta[:p], theta[p:]

    # Makes one list of angles one item longer by blending its neighbours.
    def grow(v):
        out = np.zeros(p + 1)
        for i in range(p + 1):
            left = v[i - 1] if i - 1 >= 0 else 0.0
            right = v[i] if i < p else 0.0
            out[i] = (i / p) * left + ((p - i) / p) * right
        return out
    return np.concatenate([grow(gam), grow(bet)])


# ================================================================== runner
# Training the angles: finds the best gamma and beta dial settings for this venue.
# Returns the settings, a log of scores, and how long training took.
# The real hardware runner uses this too, so training always happens on this computer.
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


# Runs the whole quantum method on a simulator and returns the standard answer sheet.
# Trains the dials, runs the program many times (shots), then marks the results.
# Refuses venues needing more than 16 qubits, as simulating them gets too slow.
def run_qaoa(problem: RoutingProblem, cfg: QAOAConfig, solver_name: str,
             trained: dict | None = None, reference: SolverResult | None = None) -> SolverResult:
    """
    trained:   output of optimise_parameters for the same problem and reps; skips training.
    reference: output of solve_exact for the same problem; skips recomputing it.
    """
    if problem.num_qubits > 16:
        raise ValueError(f"{problem.num_qubits} qubits is beyond the QAOA simulation limit (16).")
    t0 = time.perf_counter()
    # The exact classical answer is needed to grade the quantum results, so get it first
    # unless the caller already has it.
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
    # "Transpile" means rewriting the program into the gates and wiring the machine actually has,
    # much like translating a recipe into the tools a particular kitchen owns.
    sim, tkw, noise_desc = make_simulator(cfg)
    logical, params = build_qaoa_circuit(problem, cfg.reps, measure=True)
    compiled = transpile(logical, optimization_level=1, seed_transpiler=cfg.seed, **tkw)

    # Runs the program a number of times with dial settings t, and returns the share of each plan.
    def sample(t, shots):
        bound = compiled.assign_parameters(dict(zip(params, t)))
        counts = sim.run(bound, shots=shots).result().get_counts()
        return counts_to_probs(counts, n)

    energies = problem.all_energies()

    # 3. Optional fine tuning under noise, warm started from the ideal optimum.
    noisy_evals = 0
    if cfg.noise and cfg.optimise_under_noise:
        # The score under noise: average plan cost from a smaller batch of shots.
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

    # 5. Report the best plan seen, labelled best possible, valid, or not valid.
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


# Shortcut: the quantum method on a perfect simulator with no noise.
def solve_qaoa_ideal(problem: RoutingProblem, trained: dict | None = None,
                     reference: SolverResult | None = None, **kw) -> SolverResult:
    return run_qaoa(problem, QAOAConfig(noise=None, **kw), "qaoa_ideal", trained, reference)


# Shortcut: the quantum method on a simulator with realistic errors added.
# The dials are trained without noise, then reused as they would be on real hardware.
def solve_qaoa_noisy(problem: RoutingProblem, noise: str = "depolarizing", trained: dict | None = None,
                     reference: SolverResult | None = None, **kw) -> SolverResult:
    return run_qaoa(problem, QAOAConfig(noise=noise, **kw), "qaoa_noisy", trained, reference)
