"""
Classical solver using Google OR-Tools CP-SAT on the *same* objective.

Quadratic congestion terms are modelled exactly with integer resource loads and
load^2 variables; pairwise overflow terms use AND variables. CP-SAT needs integer
coefficients, so the objective is scaled and rounded. The returned plan is always
re-scored with RoutingProblem.evaluate, so reported numbers are exact.

This is the baseline that scales past what brute force can enumerate.
"""
from __future__ import annotations

import time

from ortools.sat.python import cp_model

from app.core.problem import RoutingProblem
from app.core.solvers.base import SolverResult

SCALE = 1_000_000_000  # one scale for every term; int64 has ample headroom


def solve_cpsat(problem: RoutingProblem, time_limit_s: float = 10.0, workers: int = 8) -> SolverResult:
    t0 = time.perf_counter()
    m = cp_model.CpModel()
    x = [m.NewBoolVar(o.name) for o in problem.options]

    for idxs in problem.group_options.values():
        m.AddExactlyOne(x[i] for i in idxs)

    w = problem.weights
    lin_d, _ = problem.components["distance"]
    lin_t, _ = problem.components["time"]
    lin_o, quad_o = problem.components["overflow"]
    n_res = max(len(problem.resources), 1)

    terms = []
    for i in range(problem.num_variables):
        c = w.distance * lin_d.get(i, 0) + w.time * lin_t.get(i, 0) + w.overflow * lin_o.get(i, 0)
        if c:
            terms.append(round(c * SCALE) * x[i])

    # Congestion: (load_r / cap_r)^2 / R, with load_r an integer expression.
    for rid, users in problem.resource_users.items():
        cap = problem.resources[rid].capacity
        max_load = sum(problem.options[a].group_size for a in users)
        load = m.NewIntVar(0, max_load, f"load_{rid}")
        m.Add(load == sum(problem.options[a].group_size * x[a] for a in users))
        sq = m.NewIntVar(0, max_load ** 2, f"sq_{rid}")
        m.AddMultiplicationEquality(sq, [load, load])
        coef = round(w.congestion * SCALE / (cap ** 2 * n_res))
        if coef:
            terms.append(coef * sq)

    # Pairwise overflow terms.
    for (a, b), c in quad_o.items():
        y = m.NewBoolVar(f"and_{a}_{b}")
        m.AddBoolAnd([x[a], x[b]]).OnlyEnforceIf(y)
        m.AddBoolOr([x[a].Not(), x[b].Not()]).OnlyEnforceIf(y.Not())
        terms.append(round(w.overflow * c * SCALE) * y)

    m.Minimize(sum(terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers
    status = solver.Solve(m)
    runtime = time.perf_counter() - t0

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolverResult("classical_cpsat", "infeasible", [0] * problem.num_variables, runtime)
    bits = [int(solver.Value(v)) for v in x]
    return SolverResult.build(
        problem, "classical_cpsat", "optimal" if status == cp_model.OPTIMAL else "feasible",
        bits, runtime, cpsat_wall_time=solver.WallTime(),
    )
