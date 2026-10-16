# WHAT THIS FILE IS FOR: the simplest possible plan, used as the "before" picture.
# Every group just walks its shortest path, ignoring crowding.
# Other solvers are judged by how much they improve on this.
"""'Before optimisation' baseline: every group takes its shortest path."""
import time

from app.core.problem import RoutingProblem
from app.core.solvers.base import SolverResult


# Gives each group its shortest route, times the work and returns the scored answer sheet.
def solve_naive(problem: RoutingProblem) -> SolverResult:
    t0 = time.perf_counter()
    x = problem.naive_bitstring()
    return SolverResult.build(problem, "naive_shortest_path", "feasible", x, time.perf_counter() - t0)
