# WHAT THIS FILE IS FOR: a text demo comparing the quantum method (QAOA) with the exact classical answer.
# For each preset venue it runs QAOA on a perfect simulator, with simulated noise, and
# optionally on a simulated IBM machine, then prints a table. Run it from a terminal.
"""
Stage 2 demo: classical vs ideal QAOA vs noisy QAOA on every preset.

    cd backend
    python -m scripts.run_quantum                 # p = 2, all presets
    python -m scripts.run_quantum --reps 3 --presets micro_hall concert_venue
    python -m scripts.run_quantum --skip-fake     # faster, no FakeTorino runs
"""
import argparse
import warnings

# Hide library warnings so the printed table stays readable.
warnings.filterwarnings("ignore")

from app.core.presets import PRESETS, get_preset
from app.core.problem import RoutingProblem
from app.core.solvers import solve_exact, solve_qaoa_ideal, solve_qaoa_noisy


# Reads the options typed on the command line, runs every chosen venue and prints the results.
# The table shows the chance of the best plan, the chance of a valid plan, the average
# quality (AR, approximation ratio), circuit size and time, with random guessing for comparison.
def main():
    # The options you can type after the command, each with a default value.
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--presets", nargs="*", default=list(PRESETS))
    ap.add_argument("--fake-backend", default="FakeTorino")
    ap.add_argument("--skip-fake", action="store_true")
    a = ap.parse_args()

    # Solve each venue: exact answer first, then the quantum runs.
    for pid in a.presets:
        problem = RoutingProblem(get_preset(pid))
        exact = solve_exact(problem)
        runs = [
            ("Ideal QAOA", solve_qaoa_ideal(problem, reps=a.reps, shots=a.shots)),
            ("Noisy (depol x1)", solve_qaoa_noisy(problem, noise="depolarizing", noise_level=1,
                                                  reps=a.reps, shots=a.shots)),
        ]
        if not a.skip_fake:
            runs.append((f"Noisy ({a.fake_backend})", solve_qaoa_noisy(
                problem, noise="fake_backend", fake_backend=a.fake_backend, reps=a.reps, shots=a.shots)))

        # Print the comparison table for this venue.
        rb = runs[0][1].extra["metrics"]["random_baseline"]
        print(f"\n=== {problem.venue.name}: {problem.num_qubits} qubits, p = {a.reps}")
        print(f"{'method':<22}{'P(optimal)':>11}{'P(valid)':>10}{'mean AR':>9}{'best=opt':>10}{'2q gates':>10}{'time s':>8}")
        print(f"{'Classical exact':<22}{1:>11.3f}{1:>10.3f}{1:>9.3f}{'yes':>10}{'':>10}{exact.runtime_s:>8.2f}")
        for name, r in runs:
            m = r.extra["metrics"]
            print(f"{name:<22}{m['prob_optimal']:>11.3f}{m['prob_feasible']:>10.3f}{m['mean_approx_ratio']:>9.3f}"
                  f"{'yes' if m['best_sampled']['is_optimal'] else 'no':>10}"
                  f"{r.extra['circuit']['transpiled']['two_qubit_gates']:>10}{r.runtime_s:>8.2f}")
        print(f"{'Random guessing':<22}{rb['prob_optimal']:>11.3f}{rb['prob_feasible']:>10.3f}{rb['mean_approx_ratio']:>9.3f}")


# Runs the demo only when this file is started directly.
if __name__ == "__main__":
    main()
