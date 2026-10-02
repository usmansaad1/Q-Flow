"""
Charts (PNG) and CSV exports for stored experiments.

    export_experiment(store, exp_id, out_dir)  ->  runs.csv, summary.csv, <kind>.png

These are static figures for the report. The Stage 4 dashboard draws its own
interactive charts from the same API data.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from app.core.storage import Storage  # noqa: E402

COLORS = {
    "Classical exact": "#1f2937", "Classical CP SAT": "#6b7280", "Naive (nearest exit)": "#d97706",
    "QAOA ideal": "#2563eb", "Random guessing": "#9ca3af",
}
NOISY = "#dc2626"
DEVICE = ["#7c3aed", "#059669", "#db2777"]

plt.rcParams.update({"figure.dpi": 130, "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 9})


def _color(method: str, i: int = 0) -> str:
    if method in COLORS:
        return COLORS[method]
    if method.startswith("QAOA noisy") or method == "Depolarising":
        return NOISY
    return DEVICE[i % len(DEVICE)]


def _agg(runs, key, metric):
    """{x: (mean, std)} for one metric."""
    g = defaultdict(list)
    for r in runs:
        if r.get(metric) is not None:
            g[r[key]].append(r[metric])
    return {x: (mean(v), pstdev(v) if len(v) > 1 else 0.0) for x, v in sorted(g.items())}


def _by(runs, field):
    out = defaultdict(list)
    for r in runs:
        out[r[field]].append(r)
    return out


def _line(ax, runs, x, metric, label, color, style="-", marker="o"):
    a = _agg(runs, x, metric)
    if not a:
        return
    xs = list(a)
    ax.errorbar(xs, [a[k][0] for k in xs], yerr=[a[k][1] for k in xs], label=label, color=color,
                linestyle=style, marker=marker, capsize=3, linewidth=1.6, markersize=4)


# ================================================================= charts
def chart_scaling(runs, path):
    quantum = [r for r in runs if r["method"].startswith("QAOA")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    for method, rs in _by(quantum, "method").items():
        for ax, metric in zip(axes, ("prob_optimal", "prob_feasible", "mean_approx_ratio")):
            _line(ax, rs, "num_qubits", metric, method, _color(method))
    ref = [r for r in runs if r["method"] == "QAOA ideal"]
    _line(axes[0], ref, "num_qubits", "random_prob_optimal", "Random guessing", COLORS["Random guessing"], "--", "x")
    _line(axes[2], ref, "num_qubits", "random_mean_ratio", "Random guessing", COLORS["Random guessing"], "--", "x")
    axes[0].set_yscale("log")
    for ax, t in zip(axes, ("P(optimal plan), log scale", "P(valid plan)", "Mean approximation ratio")):
        ax.set_title(t); ax.set_xlabel("Qubits (decision variables)")
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.axhline(1.0, color=COLORS["Classical exact"], linestyle=":", linewidth=1)
    axes[1].set_ylim(0, 1.05); axes[2].set_ylim(0, 1.05)
    axes[0].legend(fontsize=7)
    fig.suptitle("Experiment 1: QAOA quality vs problem size (classical exact = 1.0, dotted)", fontsize=10)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def chart_noise(runs, path):
    depol = [r for r in runs if r["method"] == "Depolarising"]
    devices = [r for r in runs if r["method"] != "Depolarising"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    for i, (inst, rs) in enumerate(_by(depol, "instance").items()):
        c = plt.cm.viridis(i / max(len(_by(depol, "instance")) - 1, 1))
        _line(axes[0], rs, "noise_level", "mean_approx_ratio", inst, c)
        _line(axes[1], rs, "noise_level", "prob_feasible", inst, c)
    for ax, t in zip(axes[:2], ("Mean approximation ratio", "P(valid plan)")):
        ax.set_title(t); ax.set_xlabel("Noise level (x baseline error rates)"); ax.set_ylim(0, 1.05)
        ax.set_xscale("symlog", linthresh=1)
        levels = sorted({r["noise_level"] for r in depol})
        ax.set_xticks(levels)
        ax.set_xticklabels([f"{l:g}" for l in levels])
        ax.minorticks_off()
    axes[0].legend(fontsize=7)
    # Device models vs ideal and baseline depolarising, per venue.
    insts = list(_by(runs, "instance"))
    series = [("Ideal", lambda r: r["method"] == "Depolarising" and r["noise_level"] == 0, COLORS["QAOA ideal"]),
              ("Depolarising x1", lambda r: r["method"] == "Depolarising" and r["noise_level"] == 1, NOISY)]
    for i, dev in enumerate(sorted({r["method"] for r in devices})):
        series.append((dev, lambda r, d=dev: r["method"] == d, DEVICE[i % len(DEVICE)]))
    width = 0.8 / len(series)
    for j, (label, pred, color) in enumerate(series):
        vals = []
        for inst in insts:
            m = [r["mean_approx_ratio"] for r in runs if r["instance"] == inst and pred(r)]
            vals.append(m[0] if m else 0)
        axes[2].bar([k + j * width for k in range(len(insts))], vals, width, label=label, color=color)
    axes[2].set_xticks([k + width * (len(series) - 1) / 2 for k in range(len(insts))])
    axes[2].set_xticklabels([i.replace(" ", "\n", 1) for i in insts], fontsize=7)
    axes[2].set_title("Real device noise models"); axes[2].set_ylim(0, 1.05); axes[2].legend(fontsize=7)
    fig.suptitle("Experiment 2: Effect of quantum noise (parameters fixed per venue)", fontsize=10)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def chart_depth(runs, path):
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    insts = _by(runs, "instance")
    for i, (inst, rs) in enumerate(insts.items()):
        c = plt.cm.viridis(i / max(len(insts) - 1, 1))
        ideal = [r for r in rs if r["method"] == "QAOA ideal"]
        noisy = [r for r in rs if r["method"].startswith("QAOA noisy")]
        _line(axes[0], ideal, "reps", "mean_approx_ratio", f"{inst} ideal", c)
        _line(axes[0], noisy, "reps", "mean_approx_ratio", f"{inst} noisy", c, "--", "s")
        _line(axes[1], ideal, "reps", "prob_optimal", f"{inst} ideal", c)
        _line(axes[1], noisy, "reps", "prob_optimal", f"{inst} noisy", c, "--", "s")
        _line(axes[2], noisy, "reps", "two_qubit_gates", inst, c)
    axes[0].set_title("Mean approximation ratio (solid ideal, dashed noisy)"); axes[0].set_ylim(0, 1.05)
    axes[1].set_title("P(optimal plan)"); axes[2].set_title("Two qubit gates in circuit")
    for ax in axes:
        ax.set_xlabel("QAOA depth p")
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    axes[2].legend(fontsize=7)
    fig.suptitle("Experiment 3: Effect of QAOA depth", fontsize=10)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def chart_versus(runs, path):
    insts = list(_by(runs, "instance"))
    methods = list(dict.fromkeys(r["method"] for r in runs))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    width = 0.8 / len(methods)
    for ax, metric, title in ((axes[0], "mean_approx_ratio", "Mean approximation ratio"),
                              (axes[1], "prob_optimal", "P(optimal plan)"),
                              (axes[2], "runtime_s", "Runtime (s), log scale\nquantum = training + simulation")):
        for j, m in enumerate(methods):
            vals = []
            for inst in insts:
                v = [r[metric] for r in runs if r["instance"] == inst and r["method"] == m]
                vals.append(v[0] if v and v[0] is not None else 0)
            ax.bar([k + j * width for k in range(len(insts))], vals, width, label=m, color=_color(m, j))
        ax.set_xticks([k + width * (len(methods) - 1) / 2 for k in range(len(insts))])
        ax.set_xticklabels([i.replace(" ", "\n", 1) for i in insts], fontsize=7)
        ax.set_title(title)
    axes[2].set_yscale("log")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(methods), fontsize=8, frameon=False)
    fig.suptitle("Experiment 4: Quantum vs classical across venues", fontsize=10)
    fig.tight_layout(rect=(0, 0.07, 1, 1)); fig.savefig(path); plt.close(fig)


CHARTS = {"scaling": chart_scaling, "noise": chart_noise, "depth": chart_depth, "versus": chart_versus}


# ================================================================= export
def export_experiment(store: Storage, exp_id: int, out_dir: str | Path) -> dict[str, Path]:
    exp = store.get_experiment(exp_id)
    if not exp:
        raise KeyError(f"Experiment {exp_id} not found.")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runs = store.get_runs(exp_id)
    paths = {}

    if runs:
        p = out / "runs.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(runs[0]))
            w.writeheader(); w.writerows(runs)
        paths["runs"] = p
    rows = (exp.get("summary") or {}).get("rows") or []
    if rows:
        p = out / "summary.csv"
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader(); w.writerows(rows)
        paths["summary"] = p
    if runs and exp["kind"] in CHARTS:
        p = out / f"{exp['kind']}.png"
        CHARTS[exp["kind"]](runs, p)
        paths["chart"] = p
    return paths
