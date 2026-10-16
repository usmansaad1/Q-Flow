"use client";

// WHAT THIS FILE IS FOR: the Experiments page, where batches of solver runs are started and reviewed.
// Each experiment answers one research question and stores every result.
// Results can be viewed as charts, downloaded as a spreadsheet file, or deleted.

import { useCallback, useEffect, useState } from "react";

import ExperimentCharts from "@/components/experiments/ExperimentCharts";
import { useConfirm } from "@/components/ConfirmDialog";
import { Button } from "@/components/lab/Field";
import { api } from "@/lib/api";
import type { ExperimentDetail, ExperimentInfo, ExperimentKind, RunRow } from "@/lib/types";

// The four experiments on offer, each with its question and rough run times for quick and full runs.
// QAOA is the quantum method being tested; qubits are the basic units of a quantum computer.
const KINDS: { kind: ExperimentKind; title: string; question: string; quick: string; full: string }[] = [
  { kind: "scaling", title: "Problem size", question: "How does QAOA hold up as the venue needs more qubits?", quick: "about 10 s", full: "about 2 min" },
  { kind: "noise", title: "Quantum noise", question: "How much do hardware errors cost, including real IBM device models?", quick: "about 5 s", full: "about 1 min" },
  { kind: "depth", title: "Circuit depth", question: "Do more QAOA layers help, with and without noise?", quick: "about 5 s", full: "about 1 min" },
  { kind: "versus", title: "Quantum versus classical", question: "Every solver on every preset venue, including run time.", quick: "about 5 s", full: "about 30 s" },
];

// The text colour for each experiment status: amber while running, green when done, dark red if failed.
const STATUS: Record<ExperimentInfo["status"], string> = {
  running: "text-amber", done: "text-exit", failed: "text-wine",
};

// Turns the run rows into CSV text, a simple table format that spreadsheet programs open.
// Values containing commas, quotes or line breaks are wrapped in quotes so the table stays intact.
function toCsv(runs: RunRow[]): string {
  if (!runs.length) return "";
  const cols = Object.keys(runs[0]) as (keyof RunRow)[];
  const esc = (v: unknown) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  return [cols.join(","), ...runs.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}

// Saves the given text to the visitor's computer as a file with the given name.
function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

// Shows a stored date and time in the visitor's own local format.
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

// The Experiments page. The left column starts runs and lists past ones; the right shows the chosen one.
export default function ExperimentsPage() {
  // What the page remembers: all experiments, the one picked, its full results, errors, and which run is starting.
  const [list, setList] = useState<ExperimentInfo[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [ask, confirmDialog] = useConfirm();

  // Reloads the list of experiments from the server and returns it.
  const refresh = useCallback(async () => {
    try {
      const l = await api.experiments();
      setList(l);
      setError(null);
      return l;
    } catch (e) {
      setError((e as Error).message);
      return [];
    }
  }, []);

  // When the page opens: load the list and pick the newest experiment.
  useEffect(() => {
    api.experiments()
      .then((l) => { setList(l); if (l.length) setSelected((s) => s ?? l[0].id); })
      .catch((e) => setError(e.message));
  }, []);

  // Whenever a different experiment is picked, load its full results.
  useEffect(() => {
    if (selected == null) return;
    api.experiment(selected).then(setDetail).catch((e) => setError(e.message));
  }, [selected]);
  // Only show a detail that matches the current selection.
  const shown = detail && detail.id === selected ? detail : null;

  // Poll while anything is running.
  // Checks again every 2.5 seconds, so new results appear without reloading the page.
  const anyRunning = list.some((e) => e.status === "running");
  useEffect(() => {
    if (!anyRunning) return;
    const t = setInterval(async () => {
      await refresh();
      if (selected != null) api.experiment(selected).then(setDetail).catch(() => {});
    }, 2500);
    return () => clearInterval(t);
  }, [anyRunning, selected, refresh]);

  // Starts a new experiment, quick or full, then shows it straight away.
  const start = async (kind: ExperimentKind, quick: boolean) => {
    setStarting(`${kind}-${quick}`);
    try {
      const { id } = await api.startExperiment(kind, quick);
      await refresh();
      setSelected(id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(null);
    }
  };

  // Asks the user to confirm, deletes the experiment, then shows the newest one left.
  const remove = async (id: number) => {
    const ok = await ask({
      title: "Delete this experiment?",
      message: "The experiment and all of its runs will be removed. This can't be undone.",
      confirmLabel: "Delete experiment", danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteExperiment(id);
      setError(null);
    } catch (e) {
      setError(`Could not delete the experiment: ${(e as Error).message}`);
      return;
    }
    const l = await refresh();
    setSelected(l[0]?.id ?? null);
  };

  return (
    <main className="mx-auto max-w-[1440px] px-5 py-6">
      <h1 className="font-display text-3xl font-bold">Experiments</h1>
      <p className="max-w-[70ch] text-sm text-ink-soft">
        Each experiment runs many solver executions automatically and stores every result. Quick runs use small settings
        for a fast check; full runs produce the data for the report.
      </p>
      {error && <p className="mt-4 rounded-[3px] border border-wine/40 bg-white px-4 py-3 text-sm text-wine">{error}</p>}

      <div className="mt-6 grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        {/* Left column: buttons to start each experiment, then the history list */}
        <aside className="space-y-6">
          <section>
            <h2 className="font-display text-lg font-bold">Run an experiment</h2>
            <ul className="mt-2">
              {KINDS.map((k) => (
                <li key={k.kind} className="border-t border-line py-3">
                  <h3 className="font-semibold">{k.title}</h3>
                  <p className="text-sm text-ink-soft">{k.question}</p>
                  <div className="mt-2 flex gap-2">
                    <Button disabled={!!starting} onClick={() => start(k.kind, true)} title={k.quick}>Quick run</Button>
                    <Button variant="primary" disabled={!!starting} onClick={() => start(k.kind, false)} title={k.full}>Full run</Button>
                    <span className="self-center text-xs text-ink-soft">{k.full}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* Past experiments; clicking one shows it on the right */}
          <section>
            <h2 className="font-display text-lg font-bold">History</h2>
            {!list.length && <p className="mt-2 text-sm text-ink-soft">Nothing stored yet. Start with a quick run above.</p>}
            <ul className="mt-2 divide-y divide-line border-y border-line">
              {list.map((e) => (
                <li key={e.id}>
                  <button onClick={() => setSelected(e.id)}
                    className={`w-full px-2 py-2 text-left ${selected === e.id ? "bg-white" : "hover:bg-white/60"}`}>
                    <span className="flex justify-between gap-2 text-sm">
                      <span className="font-medium">{KINDS.find((k) => k.kind === e.kind)?.title}</span>
                      <span className={`num text-xs font-semibold ${STATUS[e.status]}`}>{e.status === "running" ? "Running" : e.status === "done" ? "Done" : "Failed"}</span>
                    </span>
                    <span className="num block text-xs text-ink-soft">#{e.id}, {when(e.created_at)}, {e.num_runs} runs</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </aside>

        {/* Right panel: the chosen experiment, or a hint if none is chosen */}
        <section className="min-w-0 rounded-[4px] border border-line bg-panel p-5">
          {!shown ? (
            <div className="grid min-h-[300px] place-items-center text-center text-sm text-ink-soft">
              Run an experiment, or pick one from the history, to see its results here.
            </div>
          ) : (
            <>
              {/* Title and facts, plus download, chart and delete buttons */}
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-2xl font-bold">{KINDS.find((k) => k.kind === shown.kind)?.title}</h2>
                  <p className="text-sm text-ink-soft">{KINDS.find((k) => k.kind === shown.kind)?.question}</p>
                  <p className="num mt-1 text-xs text-ink-soft">
                    Experiment #{shown.id}, started {when(shown.created_at)}, {shown.runs.length} runs
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button disabled={!shown.runs.length} onClick={() => download(`qflow_${shown.id}_${shown.kind}_runs.csv`, toCsv(shown.runs))}>
                    Download runs (CSV)
                  </Button>
                  {shown.status === "done" && (
                    <a href={api.chartUrl(shown.id)} target="_blank" rel="noreferrer"
                      className="inline-flex items-center rounded-[3px] border border-line bg-white px-3 py-1.5 text-sm font-medium hover:border-ink/50">
                      Report chart (PNG)
                    </a>
                  )}
                  <Button variant="danger" disabled={shown.status === "running"} onClick={() => remove(shown.id)}>Delete</Button>
                </div>
              </div>

              {/* Progress note while running, or the first line of the error if it failed */}
              {shown.status === "running" && (
                <p className="mt-4 rounded-[3px] bg-paper px-3 py-2 text-sm">
                  Running. {shown.runs.length} runs recorded so far; this page updates by itself.
                </p>
              )}
              {shown.status === "failed" && (
                <p className="mt-4 rounded-[3px] border border-wine/40 px-3 py-2 text-sm text-wine">
                  This experiment stopped with an error: {shown.error?.split("\n")[0]}
                </p>
              )}

              {/* The charts and tables of results */}
              <div className="mt-6"><ExperimentCharts exp={shown} /></div>

              {/* A fold out list of the settings the experiment used */}
              <details className="mt-6 border-t border-line pt-3 text-sm">
                <summary className="cursor-pointer font-semibold">Settings used</summary>
                <dl className="num mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-ink-soft">
                  {Object.entries(shown.config).map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-ink">{k.replace(/_/g, " ")}</dt>
                      <dd>{Array.isArray(v) ? v.join(", ") || "none" : String(v)}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            </>
          )}
        </section>
      </div>
      {confirmDialog}
    </main>
  );
}
