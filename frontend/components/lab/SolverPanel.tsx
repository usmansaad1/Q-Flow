"use client";

import type { ProblemSettings, QuantumSettings } from "@/lib/types";
import { Button, Field, Select, Slider } from "./Field";
import { DEVICE_MODELS, QUANTUM_QUBIT_LIMIT, SOLVERS, type SolverKey } from "./solvers";

interface Props {
  selected: SolverKey;
  onSelect: (k: SolverKey) => void;
  settings: ProblemSettings;
  onSettings: (s: ProblemSettings) => void;
  quantum: QuantumSettings;
  onQuantum: (q: QuantumSettings) => void;
  qubits: number | null;
  blocked: string | null;
  running: SolverKey | null;
  onRun: (k: SolverKey) => void;
  onRunAll: () => void;
}

export default function SolverPanel(p: Props) {
  const tooBig = p.qubits != null && p.qubits > QUANTUM_QUBIT_LIMIT;
  const sel = SOLVERS.find((s) => s.key === p.selected)!;
  const w = p.settings.weights;
  const setW = (k: keyof typeof w, v: number) => p.onSettings({ ...p.settings, weights: { ...w, [k]: v } });

  return (
    <div className="space-y-4">
      <fieldset>
        <legend className="font-display text-base font-bold">Solver</legend>
        <div className="mt-2 space-y-1">
          {SOLVERS.map((s) => {
            const disabled = !s.available || (s.quantum && tooBig);
            return (
              <label key={s.key}
                className={`flex cursor-pointer gap-2.5 rounded-[3px] border px-2.5 py-2
                  ${p.selected === s.key ? "border-ink bg-paper" : "border-transparent hover:bg-paper"}
                  ${disabled ? "cursor-not-allowed opacity-50" : ""}`}>
                <input type="radio" name="solver" className="mt-1 accent-ink" disabled={disabled}
                  checked={p.selected === s.key} onChange={() => p.onSelect(s.key)} />
                <span>
                  <span className={`block text-sm font-semibold ${s.quantum ? "text-quantum" : ""}`}>{s.label}</span>
                  <span className="block text-xs text-ink-soft">{s.description}</span>
                </span>
              </label>
            );
          })}
        </div>
        {tooBig && (
          <p className="mt-2 text-xs text-wine">
            This venue needs {p.qubits} qubits. Quantum runs are limited to {QUANTUM_QUBIT_LIMIT}; remove a crowd group or
            lower the routes per group.
          </p>
        )}
      </fieldset>

      {sel.quantum && (
        <div className="space-y-3 border-t border-line pt-3">
          <Field label="QAOA depth p" hint="More layers fit the problem better but add gates, and gates add errors.">
            <Slider value={p.quantum.reps} min={1} max={5} step={1} onChange={(v) => p.onQuantum({ ...p.quantum, reps: v })} />
          </Field>
          <Field label="Shots">
            <Select<number> value={p.quantum.shots} onChange={(v) => p.onQuantum({ ...p.quantum, shots: v })}
              options={[1024, 4096, 8192].map((n) => ({ value: n, label: n.toLocaleString() }))} />
          </Field>
          {p.selected === "qaoa_noisy" && (
            <>
              <Field label="Noise model">
                <Select<QuantumSettings["noise"]> value={p.quantum.noise}
                  onChange={(v) => p.onQuantum({ ...p.quantum, noise: v })}
                  options={[{ value: "depolarizing", label: "Adjustable error rate" },
                            { value: "fake_backend", label: "Real IBM device model" }]} />
              </Field>
              {p.quantum.noise === "depolarizing" ? (
                <Field label="Error rate" hint="1x is close to current hardware. 0x is noise free.">
                  <Slider value={p.quantum.noise_level} min={0} max={10} step={0.5}
                    format={(v) => `${v}x`} onChange={(v) => p.onQuantum({ ...p.quantum, noise_level: v })} />
                </Field>
              ) : (
                <Field label="Device" hint="Calibrated errors and qubit layout. Takes about 10 seconds.">
                  <Select<string> value={p.quantum.fake_backend} options={DEVICE_MODELS}
                    onChange={(v) => p.onQuantum({ ...p.quantum, fake_backend: v })} />
                </Field>
              )}
            </>
          )}
        </div>
      )}

      <details className="border-t border-line pt-3">
        <summary className="cursor-pointer text-sm font-semibold">Optimisation priorities</summary>
        <div className="mt-3 space-y-3">
          <Field label="Avoid congestion"><Slider value={w.congestion} min={0} max={5} step={0.5} onChange={(v) => setW("congestion", v)} /></Field>
          <Field label="Avoid overflowing capacity"><Slider value={w.overflow} min={0} max={5} step={0.5} onChange={(v) => setW("overflow", v)} /></Field>
          <Field label="Short walking distance"><Slider value={w.distance} min={0} max={5} step={0.5} onChange={(v) => setW("distance", v)} /></Field>
          <Field label="Short travel time"><Slider value={w.time} min={0} max={5} step={0.5} onChange={(v) => setW("time", v)} /></Field>
          <Field label="Routes considered per group" hint="Each extra route adds one qubit per crowd group.">
            <Select<number> value={p.settings.paths_per_group}
              onChange={(v) => p.onSettings({ ...p.settings, paths_per_group: v })}
              options={[1, 2, 3, 4].map((n) => ({ value: n, label: String(n) }))} />
          </Field>
        </div>
      </details>

      <div className="flex gap-2 border-t border-line pt-3">
        <Button variant="primary" className="flex-1" disabled={!!p.blocked || !!p.running || !sel.available || (sel.quantum && tooBig)}
          onClick={() => p.onRun(p.selected)}>
          {p.running === p.selected ? "Running…" : `Run ${sel.label}`}
        </Button>
        <Button disabled={!!p.blocked || !!p.running} onClick={p.onRunAll} title="Classical, QAOA simulator and noisy QAOA">
          Run all
        </Button>
      </div>
      {p.blocked && <p className="text-xs text-wine">{p.blocked}</p>}
    </div>
  );
}
