# WHAT THIS FILE IS FOR: the simplest possible plan, used as the "before" picture.
# Every group just walks its shortest path, ignoring crowding.
# Other solvers are judged by how much they improve on this.
"""'Before optimisation' baseline: every group takes its shortest path."""
import time

from app.core.problem import RoutingProblem
from app.core.solvers.base import SolverResult


# Gives each group its shortest route, times the work and returns the scored answer sheet.
def solve_naive(problem: RoutingProblem) -> SolverResult:
    # Start the stopwatch.
    t0 = time.perf_counter()
    # Ask the problem for the "everyone takes their shortest route" plan (built in problem.py).
    x = problem.naive_bitstring()
    # Score it and wrap it in the standard answer sheet. Its status is "feasible", not "optimal",
    # because it follows the rules but is not necessarily the best plan.
    return SolverResult.build(problem, "naive_shortest_path", "feasible", x, time.perf_counter() - t0)
