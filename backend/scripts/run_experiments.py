"""
Run the proposal's experiments, store every run in SQLite, export CSV and charts.

    cd backend
    python -m scripts.run_experiments --quick              # all four, small settings (~1 to 2 min)
    python -m scripts.run_experiments                      # all four, full settings
    python -m scripts.run_experiments scaling noise        # pick experiments
    python -m scripts.run_experiments --list               # experiments already stored
    python -m scripts.run_experiments --export 3           # re-export experiment #3

Results go to backend/results/<experiment id>_<kind>/ (runs.csv, summary.csv, chart).
The database is backend/data/qflow.db.
"""
import argparse
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from app.core.charts import export_experiment
from app.core.experiments import RUNNERS, quick_config, run_experiment
from app.core.storage import Storage, results_dir


def out_dir(exp_id: int, kind: str) -> Path:
    return results_dir() / f"{exp_id:03d}_{kind}"


def main():
    ap = argparse.ArgumentParser(description="Q-Flow experiment runner")
    ap.add_argument("experiments", nargs="*", default=["all"],
                    help=f"any of: {', '.join(RUNNERS)}, all (default)")
    ap.add_argument("--quick", action="store_true", help="small fast settings for a smoke test")
    ap.add_argument("--list", action="store_true", help="list stored experiments and exit")
    ap.add_argument("--export", type=int, metavar="ID", help="re-export an existing experiment and exit")
    a = ap.parse_args()
    store = Storage()

    if a.list:
        for e in store.list_experiments():
            print(f"#{e['id']:<4}{e['status']:<9}{e['num_runs']:>5} runs  {e['created_at']}  {e['title']}")
        return
    if a.export:
        exp = store.get_experiment(a.export)
        for k, p in export_experiment(store, a.export, out_dir(a.export, exp["kind"])).items():
            print(f"{k:<8} {p}")
        return

    unknown = [k for k in a.experiments if k not in (*RUNNERS, "all")]
    if unknown:
        ap.error(f"unknown experiment(s): {', '.join(unknown)}. Options: {', '.join(RUNNERS)}, all")
    kinds = list(RUNNERS) if "all" in a.experiments else a.experiments
    for kind in kinds:
        t0 = time.perf_counter()
        exp_id = run_experiment(kind, quick_config(kind) if a.quick else None, store)
        paths = export_experiment(store, exp_id, out_dir(exp_id, kind))
        print(f"Done in {time.perf_counter() - t0:.0f}s. Saved to {paths.get('chart', out_dir(exp_id, kind)).parent}\n")


if __name__ == "__main__":
    main()
