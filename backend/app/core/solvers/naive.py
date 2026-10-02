"""'Before optimisation' baseline: every group takes its shortest path."""
import time

from app.core.problem import RoutingProblem
from app.core.solvers.base import SolverResult


def solve_naive(problem: RoutingProblem) -> SolverResult:
    t0 = time.perf_counter()
    x = problem.naive_bitstring()
    return SolverResult.build(problem, "naive_shortest_path", "feasible", x, time.perf_counter() - t0)
