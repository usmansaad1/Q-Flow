"""
Exact classical solver: enumerates every feasible plan (one path per group).

The feasible space is prod(paths per group), far smaller than 2^n, so this is
the ground truth for every problem size the quantum side can handle. It also
returns the worst feasible energy, which the approximation ratio needs:

    approximation_ratio = (E_worst - E) / (E_worst - E_opt)   in [0, 1] for feasible E
"""
from __future__ import annotations

import itertools
import time

import numpy as np

from app.core.problem import RoutingProblem
from app.core.solvers.base import SolverResult


def solve_exact(problem: RoutingProblem, max_states: int = 2_000_000) -> SolverResult:
    t0 = time.perf_counter()
    groups = list(problem.group_options.values())
    n_states = int(np.prod([len(g) for g in groups]))
    if n_states > max_states:
        raise ValueError(f"{n_states} feasible plans exceed the exact solver limit ({max_states}).")

    Q, off = problem.qubo_matrix()
    n = problem.num_variables
    # Build all feasible bitstrings at once.
    X = np.zeros((n_states, n))
    for row, combo in enumerate(itertools.product(*groups)):
        X[row, list(combo)] = 1
    energies = np.einsum("ki,ij,kj->k", X, Q, X) + off

    best = int(np.argmin(energies))
    worst = float(energies.max())
    runtime = time.perf_counter() - t0
    n_optimal = int(np.isclose(energies, energies[best], rtol=0, atol=1e-9).sum())

    return SolverResult.build(
        problem, "classical_exact", "optimal", X[best].astype(int).tolist(), runtime,
        feasible_states=n_states,
        optimal_energy=float(energies[best]),
        worst_feasible_energy=worst,
        mean_feasible_energy=float(energies.mean()),
        num_optimal_solutions=n_optimal,
    )
