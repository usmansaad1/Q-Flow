# WHAT THIS FILE IS FOR: finds the guaranteed best plan by checking every valid plan one by one.
# It is the "answer key" that the quantum results are marked against.
# It also records the worst valid plan, so scores can be shown on a 0 to 100% scale.
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


# Lists every plan where each group has exactly one route, scores them all, and keeps the best.
# Refuses to run if there are more plans than max_states, to avoid running out of memory.
# The score ("energy") is the plan's total cost: lower means a better evacuation.
def solve_exact(problem: RoutingProblem, max_states: int = 2_000_000) -> SolverResult:
    t0 = time.perf_counter()
    groups = list(problem.group_options.values())
    n_states = int(np.prod([len(g) for g in groups]))
    if n_states > max_states:
        raise ValueError(f"{n_states} feasible plans exceed the exact solver limit ({max_states}).")

    # Step 1: fetch the cost table. QUBO is the standard "yes or no choices with costs" format.
    Q, off = problem.qubo_matrix()
    n = problem.num_variables
    # Build all feasible bitstrings at once.
    X = np.zeros((n_states, n))
    for row, combo in enumerate(itertools.product(*groups)):
        X[row, list(combo)] = 1
    # Step 2: score every plan in one go using the cost table.
    energies = np.einsum("ki,ij,kj->k", X, Q, X) + off

    # Step 3: pick the cheapest plan, note the dearest one, and count any ties for first place.
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
