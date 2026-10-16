# WHAT THIS FILE IS FOR: a quick text demo of the classical (ordinary computer) planners.
# For every ready made venue it prints how the simple, exact and CP SAT planners score,
# then lists the best evacuation route for each crowd group. Run it from a terminal.
"""
Step 1 demo: before vs after on every preset, using the shared formulation.

    cd backend
    python -m scripts.run_classical
"""
import warnings

# Hide library warnings so the printed table stays readable.
warnings.filterwarnings("ignore")

from app.core.presets import PRESETS
from app.core.problem import RoutingProblem
from app.core.solvers import solve_naive, solve_exact, solve_cpsat


# Solves each preset venue three ways and prints a comparison table and the best plan.
# "energy" is the plan's score (lower is better); "over cap" counts people above route or exit capacity.
def main():
    for pid, factory in PRESETS.items():
        # Build the puzzle for this venue and print a heading with its size.
        problem = RoutingProblem(factory())
        print(f"\n=== {problem.venue.name}  ({problem.num_qubits} qubits, "
              f"{len(problem.quadratic)} quadratic terms, {problem.venue.total_people} people)")
        print(f"{'solver':<22}{'energy':>9}{'violations':>12}{'over cap':>10}{'max util':>10}{'time ms':>10}")
        # Solve it three ways and print one table row per method.
        results = [solve_naive(problem), solve_exact(problem), solve_cpsat(problem)]
        for r in results:
            ev = r.evaluation
            print(f"{r.solver:<22}{ev['energy']:>9.4f}{ev['capacity_violations']:>12}"
                  f"{ev['people_over_capacity']:>10}{ev['max_utilisation']:>10.2f}{r.runtime_s*1000:>10.1f}")
        # Then list the route each crowd takes in the exact (best) plan.
        print("Optimal plan:")
        for route in results[1].routes(problem):
            print(f"  {route['group_id']:<22}{route['size']:>4} people  ->  {' > '.join(route['path'])}")


# Runs the demo only when this file is started directly.
if __name__ == "__main__":
    main()
