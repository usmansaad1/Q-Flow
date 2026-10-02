"""
Step 1 demo: before vs after on every preset, using the shared formulation.

    cd backend
    python -m scripts.run_classical
"""
import warnings

warnings.filterwarnings("ignore")

from app.core.presets import PRESETS
from app.core.problem import RoutingProblem
from app.core.solvers import solve_naive, solve_exact, solve_cpsat


def main():
    for pid, factory in PRESETS.items():
        problem = RoutingProblem(factory())
        print(f"\n=== {problem.venue.name}  ({problem.num_qubits} qubits, "
              f"{len(problem.quadratic)} quadratic terms, {problem.venue.total_people} people)")
        print(f"{'solver':<22}{'energy':>9}{'violations':>12}{'over cap':>10}{'max util':>10}{'time ms':>10}")
        results = [solve_naive(problem), solve_exact(problem), solve_cpsat(problem)]
        for r in results:
            ev = r.evaluation
            print(f"{r.solver:<22}{ev['energy']:>9.4f}{ev['capacity_violations']:>12}"
                  f"{ev['people_over_capacity']:>10}{ev['max_utilisation']:>10.2f}{r.runtime_s*1000:>10.1f}")
        print("Optimal plan:")
        for route in results[1].routes(problem):
            print(f"  {route['group_id']:<22}{route['size']:>4} people  ->  {' > '.join(route['path'])}")


if __name__ == "__main__":
    main()
