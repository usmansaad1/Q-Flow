"use client";

import { pct, num, seconds } from "@/lib/format";
import type { OptimizeResponse, SolverResultDTO } from "@/lib/types";
import { SOLVERS, type SolverKey } from "./solvers";

type Runs = Partial<Record<SolverKey, OptimizeResponse>>;

interface Column {
  key: string;
  label: string;
  quantum: boolean;
  result: SolverResultDTO;
  resp: OptimizeResponse;
  baseline?: boolean;
}

function quality(c: Column) {
  const q = c.resp.quality;
  if (!q) return null;
  if (c.baseline) return { typical: q.baseline_approx_ratio ?? null, chance: q.baseline_is_optimal ? 1 : 0, valid: 1 };
  return c.quantum
    ? { typical: q.mean_approx_ratio ?? null, chance: q.prob_optimal ?? null, valid: q.prob_feasible ?? null }
    : { typical: q.approximation_ratio, chance: q.is_optimal ? 1 : 0, valid: 1 };
}

export default function ResultsBoard({ runs, noiseLabel }: { runs: Runs; noiseLabel: string }) {
  const keys = SOLVERS.map((s) => s.key).filter((k) => runs[k]);
  if (!keys.length) {
    return (
      <section className="rounded-[4px] border border-dashed border-line bg-panel px-5 py-8 text-center">
        <h2 className="font-display text-lg font-bold">No results yet</h2>
        <p className="mx-auto mt-1 max-w-[60ch] text-sm text-ink-soft">
          Choose a solver and press Run, or press Run all to fill in the full classical versus quantum comparison for this venue.
        </p>
      </section>
    );
  }
  const first = runs[keys[0]]!;
  const cols: Column[] = [
    { key: "baseline", label: "Nearest exit", quantum: false, result: first.baseline, resp: first, baseline: true },
    ...keys.map((k) => {
      const s = SOLVERS.find((x) => x.key === k)!;
      return { key: k, label: k === "qaoa_noisy" ? `Noisy QAOA (${noiseLabel})` : s.label, quantum: s.quantum, result: runs[k]!.result, resp: runs[k]! };
    }),
  ];
  const random = keys.map((k) => runs[k]!.quality?.random_baseline).find(Boolean);

  const rows: { label: string; note?: string; cell: (c: Column) => React.ReactNode; strong?: boolean }[] = [
    {
      label: "Typical answer quality", strong: true,
      note: "How close an answer is to the best plan, from 0% (worst valid plan or invalid) to 100% (optimal). For quantum it is the average over every shot.",
      cell: (c) => pct(quality(c)?.typical),
    },
    {
      label: "Chance of the best plan",
      note: random ? `Random guessing would find it ${pct(random.prob_optimal, 1)} of the time.` : undefined,
      cell: (c) => pct(quality(c)?.chance, c.quantum ? 1 : 0),
    },
    { label: "Valid plans", note: "Every group sent down exactly one route.", cell: (c) => pct(quality(c)?.valid, c.quantum ? 1 : 0) },
    { label: "Objective score", note: "Lower is better.", cell: (c) => num(c.result.evaluation.energy, 3) },
    { label: "Congestion score", cell: (c) => num(c.result.evaluation.components.congestion, 3) },
    {
      label: "People over capacity",
      cell: (c) => {
        const v = c.result.evaluation.people_over_capacity;
        return <span className={v > 0 ? "font-semibold text-wine" : "text-exit"}>{v}</span>;
      },
    },
    { label: "Overloaded routes and exits", cell: (c) => c.result.evaluation.capacity_violations },
    { label: "Busiest route or exit", cell: (c) => pct(c.result.evaluation.max_utilisation) },
    { label: "Run time", note: "Quantum time is simulation on this computer, including training.", cell: (c) => c.baseline ? "" : seconds(c.result.runtime_s) },
    { label: "Qubits", cell: (c) => (c.quantum ? c.resp.problem.num_qubits : "") },
    { label: "Two qubit gates", cell: (c) => c.result.extra.circuit?.transpiled.two_qubit_gates ?? "" },
  ];

  return (
    <section className="overflow-x-auto rounded-[4px] border border-line bg-panel">
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <caption className="px-5 pb-1 pt-4 text-left">
          <span className="font-display text-lg font-bold">Comparison</span>
          <span className="ml-3 text-sm text-ink-soft">{first.problem.venue}, {first.problem.num_qubits} decision variables</span>
        </caption>
        <thead>
          <tr className="border-b border-line">
            <th className="w-[30%] px-5 py-2 text-left font-medium text-ink-soft">Measure</th>
            {cols.map((c) => (
              <th key={c.key} className={`px-4 py-2 text-right font-semibold ${c.quantum ? "text-quantum" : c.baseline ? "text-ink-soft" : ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.filter((r) => cols.some((c) => { const v = r.cell(c); return v !== "" && v != null; })).map((r) => (
            <tr key={r.label} className="border-b border-line/70 last:border-0 align-top">
              <th scope="row" className="px-5 py-2 text-left font-normal">
                <span className={r.strong ? "font-semibold" : ""}>{r.label}</span>
                {r.note && <span className="block text-xs text-ink-soft">{r.note}</span>}
              </th>
              {cols.map((c) => (
                <td key={c.key} className={`num px-4 py-2 text-right ${r.strong ? "font-display text-xl font-bold" : ""}`}>
                  {r.cell(c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
