"use client";
// WHAT THIS FILE IS FOR: the fold out table of past Lab runs.
// The Lab page shows it so users can reopen or delete earlier results.

import { pct } from "@/lib/format";
import type { LabRunSummary } from "@/lib/types";
import { SOLVERS } from "./solvers";

// Turns a saved timestamp into a friendly local date and time, like "12 Oct 2026, 14:05".
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

/** Every Lab run is saved automatically; reopen one to see its table and map again. */
export default function RunHistory({ runs, onOpen, onDelete }:
  { runs: LabRunSummary[]; onOpen: (id: number) => void; onDelete: (id: number) => void }) {
  return (
    <details className="rounded-[4px] border border-line bg-panel p-4">
      <summary className="cursor-pointer font-display text-base font-bold">
        Run history <span className="num font-sans text-sm font-normal text-ink-soft">({runs.length} saved)</span>
      </summary>
      {!runs.length ? <p className="mt-2 text-sm text-ink-soft">Every run is saved here automatically.</p> : (
        <table className="mt-3 w-full text-sm">
          {/* Column titles, then one row per saved run with Open and Delete buttons */}
          <thead>
            <tr className="border-b border-line text-left text-xs text-ink-soft">
              <th className="py-1.5 font-medium">Venue</th><th className="font-medium">Solver</th>
              <th className="text-right font-medium">Qubits</th><th className="text-right font-medium">Typical quality</th>
              <th className="pl-4 font-medium">When</th><th />
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-b border-line/60 last:border-0">
                <td className="py-1.5">{r.venue_name}</td>
                <td>{SOLVERS.find((s) => s.key === r.solver)?.label ?? r.solver}</td>
                <td className="num text-right">{r.num_qubits}</td>
                <td className="num text-right">{pct(r.quality)}</td>
                <td className="num pl-4 text-ink-soft">{when(r.created_at)}</td>
                <td className="whitespace-nowrap text-right">
                  <button onClick={() => onOpen(r.id)} className="px-2 font-medium text-quantum hover:underline">Open</button>
                  <button onClick={() => onDelete(r.id)} className="px-2 text-wine hover:underline">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  );
}
