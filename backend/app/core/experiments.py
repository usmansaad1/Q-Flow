"""
The four experiments from the Q-Flow proposal.

  scaling   Exp 1  How does QAOA quality change as the number of variables grows?
                   Several random venues per size, so the trend is not an artefact
                   of one layout.
  noise     Exp 2  How does noise affect quality? Depolarising sweep plus calibrated
                   models of real IBM devices. Parameters are trained once per venue
                   and reused at every noise level, so only the noise changes.
  depth     Exp 3  How does QAOA depth p affect quality, ideal vs noisy?
  versus    Exp 4  Quantum vs classical across all preset venues, including runtime.

Every solver execution is stored as one row in SQLite, and every experiment ends
with a summary (mean and standard deviation per group) saved on the experiment.
"""
from __future__ import annotations

import traceback
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from statistics import mean, pstdev
from typing import Callable

from app.core.generator import generate_venue
from app.core.presets import PRESETS, get_preset
from app.core.problem import RoutingProblem
from app.core.solvers import solve_naive, solve_exact, solve_cpsat
from app.core.solvers.base import SolverResult
from app.core.solvers.quantum import optimise_parameters, solve_qaoa_ideal, solve_qaoa_noisy
from app.core.storage import Storage

Progress = Callable[[str], None]


# ================================================================ configs
@dataclass
class ScalingConfig:
    sizes: list[int] = field(default_factory=lambda: [4, 6, 8, 10, 12])
    instances: int = 5
    reps: int = 2
    shots: int = 4096
    noise_level: float = 1.0


@dataclass
class NoiseConfig:
    presets: list[str] = field(default_factory=lambda: list(PRESETS))
    levels: list[float] = field(default_factory=lambda: [0, 0.5, 1, 2, 3, 5, 10])
    fake_backends: list[str] = field(default_factory=lambda: ["FakeTorino", "FakeBrisbane"])
    reps: int = 2
    shots: int = 4096


@dataclass
class DepthConfig:
    presets: list[str] = field(default_factory=lambda: list(PRESETS))
    reps_list: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    noise_level: float = 1.0
    shots: int = 4096


@dataclass
class VersusConfig:
    presets: list[str] = field(default_factory=lambda: list(PRESETS))
    reps: int = 2
    shots: int = 4096
    noise_level: float = 1.0
    fake_backend: str | None = "FakeTorino"


CONFIGS = {"scaling": ScalingConfig, "noise": NoiseConfig, "depth": DepthConfig, "versus": VersusConfig}

TITLES = {
    "scaling": "Exp 1: QAOA quality vs problem size",
    "noise": "Exp 2: Effect of quantum noise",
    "depth": "Exp 3: Effect of QAOA depth p",
    "versus": "Exp 4: Quantum vs classical across venues",
}


def quick_config(kind: str):
    """Small settings for a fast smoke run (about a minute in total)."""
    return {
        "scaling": ScalingConfig(sizes=[4, 6, 8], instances=2, shots=2048),
        "noise": NoiseConfig(presets=["micro_hall", "small_event_hall"], levels=[0, 1, 5], fake_backends=[], shots=2048),
        "depth": DepthConfig(presets=["micro_hall", "small_event_hall"], reps_list=[1, 2, 3], shots=2048),
        "versus": VersusConfig(presets=["micro_hall", "small_event_hall"], fake_backend=None, shots=2048),
    }[kind]


# ================================================================ records
def make_record(exp_id: int, instance: str, problem: RoutingProblem, method: str,
                result: SolverResult, reference: SolverResult, noise_level: float | None = None) -> dict:
    """Flatten a SolverResult into a storage row. Classical answers are deterministic,
    so their 'probability of optimum' is simply 1 or 0."""
    e_opt = reference.extra["optimal_energy"]
    e_worst = reference.extra["worst_feasible_energy"]
    span = (e_worst - e_opt) or 1.0
    energy = result.evaluation["energy"]
    is_opt = abs(energy - e_opt) < 1e-9
    rec = dict(
        experiment_id=exp_id, instance=instance, num_qubits=problem.num_qubits, method=method,
        solver=result.solver, energy=energy, optimal_energy=e_opt, runtime_s=result.runtime_s,
        best_is_optimal=int(is_opt), noise_level=noise_level,
    )
    m = result.extra.get("metrics")
    if m:  # quantum
        circ = result.extra["circuit"]["transpiled"]
        cfg = result.extra["config"]
        rec.update(
            noise_model=result.extra["noise_model"], reps=cfg["reps"], shots=cfg["shots"],
            prob_optimal=m["prob_optimal"], prob_feasible=m["prob_feasible"],
            mean_approx_ratio=m["mean_approx_ratio"], best_is_optimal=int(m["best_sampled"]["is_optimal"]),
            random_prob_optimal=m["random_baseline"]["prob_optimal"],
            random_mean_ratio=m["random_baseline"]["mean_approx_ratio"],
            two_qubit_gates=circ["two_qubit_gates"], depth=circ["depth"],
            details={"parameters": result.extra["parameters"], "top_bitstrings": m["top_bitstrings"][:5],
                     "most_likely": m["most_likely"], "evaluations": result.extra["evaluations"]},
        )
    else:  # classical
        feasible = result.evaluation["feasible"]
        rec.update(
            prob_optimal=float(is_opt), prob_feasible=float(feasible),
            mean_approx_ratio=max(0.0, min(1.0, (e_worst - energy) / span)) if feasible else 0.0,
            details={"capacity_violations": result.evaluation["capacity_violations"],
                     "people_over_capacity": result.evaluation["people_over_capacity"]},
        )
    return rec


def summarise(runs: list[dict], x_key: str) -> list[dict]:
    """Mean and population standard deviation per (x value, method)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in runs:
        groups[(r[x_key], r["method"])].append(r)
    out = []
    for (x, method), rs in sorted(groups.items(), key=lambda kv: (str(kv[0][1]), _sortable(kv[0][0]))):
        row = {x_key: x, "method": method, "n": len(rs)}
        for metric in ("prob_optimal", "prob_feasible", "mean_approx_ratio", "runtime_s",
                       "two_qubit_gates", "random_prob_optimal", "random_mean_ratio"):
            vals = [r[metric] for r in rs if r.get(metric) is not None]
            if vals:
                row[metric] = mean(vals)
                row[f"{metric}_std"] = pstdev(vals) if len(vals) > 1 else 0.0
        out.append(row)
    return out


def _sortable(v):
    return (0, v) if isinstance(v, (int, float)) else (1, str(v))


# ============================================================ experiments
def _quantum_pair(store, exp_id, label, problem, reference, reps, shots, noise_level, log, trained=None):
    trained = trained or optimise_parameters(problem, reps)
    ideal = solve_qaoa_ideal(problem, reps=reps, shots=shots, trained=trained, reference=reference)
    store.add_run(make_record(exp_id, label, problem, "QAOA ideal", ideal, reference, 0.0))
    noisy = solve_qaoa_noisy(problem, noise="depolarizing", noise_level=noise_level, reps=reps, shots=shots,
                             trained=trained, reference=reference)
    store.add_run(make_record(exp_id, label, problem, f"QAOA noisy x{noise_level:g}", noisy, reference, noise_level))
    log(f"  {label:<26} ideal P(opt)={ideal.extra['metrics']['prob_optimal']:.3f}  "
        f"noisy P(opt)={noisy.extra['metrics']['prob_optimal']:.3f}")


def run_scaling(store: Storage, exp_id: int, cfg: ScalingConfig, log: Progress) -> list[dict]:
    for size in cfg.sizes:
        if size % 2:
            raise ValueError("Scaling sizes must be even (2 qubits per crowd group).")
        log(f"{size} qubits")
        for i in range(cfg.instances):
            venue = generate_venue(size // 2, seed=1000 * size + i)
            problem = RoutingProblem(venue, paths_per_group=2)
            reference = solve_exact(problem)
            store.add_run(make_record(exp_id, venue.name, problem, "Classical exact", reference, reference))
            store.add_run(make_record(exp_id, venue.name, problem, "Classical CP SAT", solve_cpsat(problem), reference))
            _quantum_pair(store, exp_id, venue.name, problem, reference, cfg.reps, cfg.shots, cfg.noise_level, log)
    return summarise(store.get_runs(exp_id), "num_qubits")


def run_noise(store: Storage, exp_id: int, cfg: NoiseConfig, log: Progress) -> list[dict]:
    for pid in cfg.presets:
        problem = RoutingProblem(get_preset(pid))
        reference = solve_exact(problem)
        trained = optimise_parameters(problem, cfg.reps)
        log(f"{problem.venue.name} ({problem.num_qubits} qubits)")
        for level in cfg.levels:
            r = solve_qaoa_noisy(problem, noise="depolarizing", noise_level=level, reps=cfg.reps,
                                 shots=cfg.shots, trained=trained, reference=reference)
            store.add_run(make_record(exp_id, problem.venue.name, problem, "Depolarising", r, reference, level))
            log(f"  depolarising x{level:<5g} mean AR={r.extra['metrics']['mean_approx_ratio']:.3f}")
        for fb in cfg.fake_backends:
            r = solve_qaoa_noisy(problem, noise="fake_backend", fake_backend=fb, reps=cfg.reps,
                                 shots=cfg.shots, trained=trained, reference=reference)
            store.add_run(make_record(exp_id, problem.venue.name, problem, fb, r, reference))
            log(f"  {fb:<18} mean AR={r.extra['metrics']['mean_approx_ratio']:.3f}")
    return summarise(store.get_runs(exp_id), "noise_level")


def run_depth(store: Storage, exp_id: int, cfg: DepthConfig, log: Progress) -> list[dict]:
    for pid in cfg.presets:
        problem = RoutingProblem(get_preset(pid))
        reference = solve_exact(problem)
        log(f"{problem.venue.name} ({problem.num_qubits} qubits)")
        for reps in cfg.reps_list:
            log(f" p = {reps}")
            _quantum_pair(store, exp_id, problem.venue.name, problem, reference,
                          reps, cfg.shots, cfg.noise_level, log)
    return summarise(store.get_runs(exp_id), "reps")


def run_versus(store: Storage, exp_id: int, cfg: VersusConfig, log: Progress) -> list[dict]:
    for pid in cfg.presets:
        problem = RoutingProblem(get_preset(pid))
        name = problem.venue.name
        log(f"{name} ({problem.num_qubits} qubits)")
        reference = solve_exact(problem)
        store.add_run(make_record(exp_id, name, problem, "Naive (nearest exit)", solve_naive(problem), reference))
        store.add_run(make_record(exp_id, name, problem, "Classical exact", reference, reference))
        store.add_run(make_record(exp_id, name, problem, "Classical CP SAT", solve_cpsat(problem), reference))
        trained = optimise_parameters(problem, cfg.reps)
        _quantum_pair(store, exp_id, name, problem, reference, cfg.reps, cfg.shots, cfg.noise_level, log, trained)
        if cfg.fake_backend:
            r = solve_qaoa_noisy(problem, noise="fake_backend", fake_backend=cfg.fake_backend, reps=cfg.reps,
                                 shots=cfg.shots, trained=trained, reference=reference)
            store.add_run(make_record(exp_id, name, problem, f"QAOA {cfg.fake_backend}", r, reference))
    return summarise(store.get_runs(exp_id), "instance")


RUNNERS = {"scaling": run_scaling, "noise": run_noise, "depth": run_depth, "versus": run_versus}


def run_experiment(kind: str, config=None, store: Storage | None = None, log: Progress = print,
                   exp_id: int | None = None) -> int:
    """Create (or reuse) an experiment row, run it, store the summary. Returns its id."""
    if kind not in RUNNERS:
        raise ValueError(f"Unknown experiment '{kind}'. Options: {', '.join(RUNNERS)}")
    store = store or Storage()
    config = config or CONFIGS[kind]()
    if exp_id is None:
        exp_id = store.create_experiment(kind, TITLES[kind], asdict(config))
    log(f"[{TITLES[kind]}] experiment #{exp_id}")
    try:
        summary = RUNNERS[kind](store, exp_id, config, log)
        store.finish_experiment(exp_id, {"rows": summary})
    except Exception as e:
        store.finish_experiment(exp_id, error=f"{e}\n{traceback.format_exc()}")
        raise
    return exp_id
