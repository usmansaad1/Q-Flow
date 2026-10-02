"use client";

import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { pct, seconds } from "@/lib/format";
import type { ExperimentDetail, RunRow } from "@/lib/types";

const C = {
  ideal: "#4B3FD1", noisy: "#D9482B", random: "#9AA6B5", classical: "#15233F", naive: "#E2A11B",
  series: ["#15233F", "#0E7490", "#B45309", "#6B7280", "#7A1F3D", "#4D7C0F"],
  devices: ["#7A1F3D", "#0E7490", "#6B7280"],
};
const AXIS = { fontSize: 11, fill: "#5A6478" };

type Metric = keyof Pick<RunRow, "prob_optimal" | "prob_feasible" | "mean_approx_ratio" | "random_prob_optimal" |
  "random_mean_ratio" | "two_qubit_gates" | "runtime_s">;

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

/** One row per x value; one column per series, averaged over runs. */
function table(runs: RunRow[], x: (r: RunRow) => string | number, series: (r: RunRow) => string | null, metric: Metric) {
  const acc = new Map<string | number, Map<string, number[]>>();
  for (const r of runs) {
    const s = series(r);
    const v = r[metric];
    if (s == null || v == null) continue;
    const row = acc.get(x(r)) ?? new Map();
    row.set(s, [...(row.get(s) ?? []), v]);
    acc.set(x(r), row);
  }
  return [...acc.entries()]
    .sort(([a], [b]) => (typeof a === "number" && typeof b === "number" ? a - b : 0))
    .map(([xv, row]) => ({ x: xv, ...Object.fromEntries([...row].map(([k, v]) => [k, mean(v)])) }));
}

const seriesNames = (rows: Record<string, unknown>[]) => [...new Set(rows.flatMap((r) => Object.keys(r).filter((k) => k !== "x")))];

function Panel({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <figure className="min-w-0">
      <figcaption>
        <span className="font-display text-base font-bold">{title}</span>
        {note && <span className="block text-xs text-ink-soft">{note}</span>}
      </figcaption>
      <div className="mt-2 h-[280px]">{children}</div>
    </figure>
  );
}

function Lines({ data, xLabel, percent = true, log = false, fit = false, colors, dashed = [] }: {
  data: Record<string, unknown>[]; xLabel: string; percent?: boolean; log?: boolean; fit?: boolean;
  colors: Record<string, string> | string[]; dashed?: string[];
}) {
  const names = seriesNames(data);
  const color = (n: string, i: number) => (Array.isArray(colors) ? colors[i % colors.length] : colors[n] ?? C.series[i % C.series.length]);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 12, bottom: 16, left: 0 }}>
        <CartesianGrid stroke="#E4E9EF" />
        <XAxis dataKey="x" tick={AXIS} label={{ value: xLabel, position: "insideBottom", offset: -10, ...AXIS }} />
        <YAxis tick={AXIS} width={48} scale={log ? "log" : "auto"}
          domain={log ? [(min: number) => min * 0.6, 1]
            : percent && fit ? [0, (max: number) => Math.min(1, Math.max(0.05, max * 1.25))]
            : percent ? [0, 1] : ["auto", "auto"]}
          tickFormatter={(v) => (percent ? pct(v, log && v < 0.01 ? 1 : 0) : String(v))} />
        <Tooltip formatter={(v) => (percent ? pct(Number(v), 1) : String(Math.round(Number(v))))} labelFormatter={(l) => `${xLabel}: ${l}`} />
        <Legend verticalAlign="top" align="right" height={26} iconType="plainline" itemSorter={null} wrapperStyle={{ fontSize: 11 }} />
        {names.map((n, i) => (
          <Line key={n} type="linear" dataKey={n} stroke={color(n, i)} strokeWidth={2}
            dot={dashed.includes(n) ? false : { r: 3 }}
            strokeDasharray={dashed.includes(n) ? "5 4" : undefined} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function Bars({ data, colors, log = false, percent = true }: {
  data: Record<string, unknown>[]; colors: Record<string, string> | string[]; log?: boolean; percent?: boolean;
}) {
  const names = seriesNames(data);
  const color = (n: string, i: number) => (Array.isArray(colors) ? colors[i % colors.length] : colors[n] ?? C.series[i % C.series.length]);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 6, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid stroke="#E4E9EF" vertical={false} />
        <XAxis dataKey="x" tick={AXIS} interval={0} />
        <YAxis tick={AXIS} width={56} scale={log ? "log" : "auto"}
          domain={log ? [(min: number) => min * 0.5, (max: number) => max * 2] : percent ? [0, 1] : ["auto", "auto"]}
          tickFormatter={(v) => (percent ? pct(v) : seconds(v))} />
        <Tooltip formatter={(v) => (percent ? pct(Number(v), 1) : seconds(Number(v)))} />
        <Legend verticalAlign="top" align="right" height={26} itemSorter={null} wrapperStyle={{ fontSize: 11 }} />
        {names.map((n, i) => <Bar key={n} dataKey={n} fill={color(n, i)} isAnimationActive={false} />)}
      </BarChart>
    </ResponsiveContainer>
  );
}

// ================================================================ per kind
function Scaling({ runs }: { runs: RunRow[] }) {
  const q = runs.filter((r) => r.method.startsWith("QAOA"));
  const ideal = q.filter((r) => r.method === "QAOA ideal");
  const label = (r: RunRow) => (r.method === "QAOA ideal" ? "QAOA ideal" : "QAOA noisy");
  const withRandom = (metric: Metric, rmetric: Metric) => {
    const a = table(q, (r) => r.num_qubits, label, metric);
    const b = table(ideal, (r) => r.num_qubits, () => "Random guessing", rmetric);
    return a.map((row) => ({ ...row, ...b.find((x) => x.x === row.x) }));
  };
  const colors = { "QAOA ideal": C.ideal, "QAOA noisy": C.noisy, "Random guessing": C.random };
  return (
    <div className="grid gap-8 xl:grid-cols-3">
      <Panel title="Chance of the best plan" note="Per shot, log scale. Classical exact is always 100%.">
        <Lines data={withRandom("prob_optimal", "random_prob_optimal")} xLabel="Qubits" log colors={colors} dashed={["Random guessing"]} />
      </Panel>
      <Panel title="Typical answer quality" note="Mean approximation ratio over all shots.">
        <Lines data={withRandom("mean_approx_ratio", "random_mean_ratio")} xLabel="Qubits" colors={colors} dashed={["Random guessing"]} />
      </Panel>
      <Panel title="Valid plans" note="Shots where every group gets exactly one route.">
        <Lines data={table(q, (r) => r.num_qubits, label, "prob_feasible")} xLabel="Qubits" colors={colors} />
      </Panel>
    </div>
  );
}

function Noise({ runs }: { runs: RunRow[] }) {
  const depol = runs.filter((r) => r.method === "Depolarising");
  const devices = [...new Set(runs.filter((r) => r.method !== "Depolarising").map((r) => r.method))];
  const deviceRows = table(runs, (r) => r.instance, (r) =>
    r.method === "Depolarising" ? (r.noise_level === 0 ? "Ideal" : r.noise_level === 1 ? "Errors 1x" : null) : r.method.replace("Fake", "IBM "),
  "mean_approx_ratio");
  return (
    <div className="grid gap-8 xl:grid-cols-3">
      <Panel title="Typical answer quality" note="As the error rate rises. 1x is close to current hardware.">
        <Lines data={table(depol, (r) => r.noise_level ?? 0, (r) => r.instance, "mean_approx_ratio")} xLabel="Error rate (x)" colors={C.series} />
      </Panel>
      <Panel title="Valid plans">
        <Lines data={table(depol, (r) => r.noise_level ?? 0, (r) => r.instance, "prob_feasible")} xLabel="Error rate (x)" colors={C.series} />
      </Panel>
      {devices.length > 0 && (
        <Panel title="Real device noise models" note="Calibrated errors and qubit layout of IBM processors.">
          <Bars data={deviceRows} colors={{ Ideal: C.ideal, "Errors 1x": C.noisy, ...Object.fromEntries(devices.map((d, i) => [d.replace("Fake", "IBM "), C.devices[i % 3]])) }} />
        </Panel>
      )}
    </div>
  );
}

function Depth({ runs }: { runs: RunRow[] }) {
  const venues = [...new Set(runs.map((r) => r.instance))];
  const [venue, setVenue] = useState(venues[0]);
  const vr = runs.filter((r) => r.instance === venue);
  const label = (r: RunRow) => (r.method === "QAOA ideal" ? "Ideal" : "Noisy");
  const colors = { Ideal: C.ideal, Noisy: C.noisy };
  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-1" role="group" aria-label="Venue">
        {venues.map((v) => (
          <button key={v} onClick={() => setVenue(v)}
            className={`rounded-[2px] border px-2.5 py-1 text-[13px] ${venue === v ? "border-ink bg-ink text-white" : "border-line bg-white text-ink-soft hover:text-ink"}`}>
            {v}
          </button>
        ))}
      </div>
      <div className="grid gap-8 xl:grid-cols-3">
        <Panel title="Typical answer quality" note="Ideal keeps improving with depth; noise eventually wins.">
          <Lines data={table(vr, (r) => r.reps ?? 0, label, "mean_approx_ratio")} xLabel="QAOA depth p" colors={colors} />
        </Panel>
        <Panel title="Chance of the best plan">
          <Lines data={table(vr, (r) => r.reps ?? 0, label, "prob_optimal")} xLabel="QAOA depth p" colors={colors} fit />
        </Panel>
        <Panel title="Two qubit gates" note="The main source of hardware error.">
          <Lines data={table(vr.filter((r) => r.method !== "QAOA ideal"), (r) => r.reps ?? 0, () => "Gates", "two_qubit_gates")}
            xLabel="QAOA depth p" percent={false} colors={[C.classical]} />
        </Panel>
      </div>
    </div>
  );
}

function Versus({ runs }: { runs: RunRow[] }) {
  const methods = [...new Set(runs.map((r) => r.method))];
  const colorOf = (m: string) => m.startsWith("Naive") ? C.naive : m.startsWith("Classical exact") ? C.classical
    : m.startsWith("Classical") ? "#6B7280" : m === "QAOA ideal" ? C.ideal : m.startsWith("QAOA noisy") ? C.noisy : C.devices[0];
  const colors = Object.fromEntries(methods.map((m) => [m, colorOf(m)]));
  const short = (v: string) => v.replace(" Venue", "").replace(" Centre", "").replace(" Hall", "");
  const rows = (metric: Metric) => table(runs, (r) => short(r.instance), (r) => r.method, metric);
  return (
    <div className="grid gap-8 xl:grid-cols-2">
      <Panel title="Typical answer quality" note="Classical solvers find the best plan every time.">
        <Bars data={rows("mean_approx_ratio")} colors={colors} />
      </Panel>
      <Panel title="Run time" note="Log scale. Quantum time is simulation including training.">
        <Bars data={table(runs.filter((r) => !r.method.startsWith("Naive")), (r) => short(r.instance), (r) => r.method, "runtime_s")}
          colors={colors} log percent={false} />
      </Panel>
    </div>
  );
}

export default function ExperimentCharts({ exp }: { exp: ExperimentDetail }) {
  if (!exp.runs.length) return <p className="text-sm text-ink-soft">No runs recorded yet.</p>;
  switch (exp.kind) {
    case "scaling": return <Scaling runs={exp.runs} />;
    case "noise": return <Noise runs={exp.runs} />;
    case "depth": return <Depth runs={exp.runs} />;
    case "versus": return <Versus runs={exp.runs} />;
  }
}
