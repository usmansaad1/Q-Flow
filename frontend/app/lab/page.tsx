"use client";

import { useEdgesState, useNodesState, type Connection } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState } from "react";

import LoadLegend from "@/components/LoadLegend";
import VenueCanvas from "@/components/VenueCanvas";
import { Button, Select, TextInput } from "@/components/lab/Field";
import Inspector from "@/components/lab/Inspector";
import PlanList from "@/components/lab/PlanList";
import ResultsBoard from "@/components/lab/ResultsBoard";
import SolverPanel from "@/components/lab/SolverPanel";
import { DEVICE_MODELS, QUANTUM_QUBIT_LIMIT, SOLVERS, type SolverKey } from "@/components/lab/solvers";
import { api } from "@/lib/api";
import { planLoads } from "@/lib/plan";
import type { OptimizeResponse, PresetInfo, ProblemSettings, ProblemSummary, QuantumSettings, VenueDTO } from "@/lib/types";
import { graphToVenue, newId, venueToGraph, type PlaceNode, type RouteEdge } from "@/lib/venue";

const DEFAULT_SETTINGS: ProblemSettings = {
  weights: { distance: 1, time: 0, congestion: 1, overflow: 2 },
  paths_per_group: 2,
  penalty_factor: 1.5,
};
const DEFAULT_QUANTUM: QuantumSettings = {
  reps: 2, shots: 4096, noise: "depolarizing", noise_level: 1, fake_backend: "FakeTorino", seed: 7,
};

type Runs = Partial<Record<SolverKey, OptimizeResponse>>;
type Shown = "baseline" | SolverKey | null;

export default function LabPage() {
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [presetId, setPresetId] = useState("small_event_hall");
  const [venueName, setVenueName] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<PlaceNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<RouteEdge>([]);
  const [canvasKey, setCanvasKey] = useState(0);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [quantum, setQuantum] = useState(DEFAULT_QUANTUM);
  const [solver, setSolver] = useState<SolverKey>("classical_exact");
  // Results remember which venue and settings they were computed for (sig);
  // anything computed for a different signature is treated as stale.
  const [results, setResults] = useState<{ sig: string | null; runs: Runs; shown: Shown; error: string | null }>(
    { sig: null, runs: {}, shown: null, error: null });
  const [running, setRunning] = useState<SolverKey | null>(null);
  const [noiseLabel, setNoiseLabel] = useState("");
  const [problem, setProblem] = useState<{ sig: string | null; summary: ProblemSummary | null; error: string | null }>(
    { sig: null, summary: null, error: null });
  const [apiError, setApiError] = useState<string | null>(null);

  // ------------------------------------------------------------ loading
  const applyVenue = useCallback((v: VenueDTO) => {
    const g = venueToGraph(v);
    setNodes(g.nodes);
    setEdges(g.edges);
    setVenueName(v.name);
    setCanvasKey((k) => k + 1);
    setApiError(null);
  }, [setNodes, setEdges]);

  const loadPreset = (id: string) =>
    api.preset(id).then(applyVenue).catch((e) => setApiError(e.message));

  useEffect(() => {
    let alive = true;
    Promise.all([api.presets(), api.preset("small_event_hall")])
      .then(([p, v]) => { if (alive) { setPresets(p); applyVenue(v); } })
      .catch((e) => { if (alive) setApiError(e.message); });
    return () => { alive = false; };
  }, [applyVenue]);

  // ---------------------------------------------- venue -> backend format
  const conversion = useMemo(() => graphToVenue(venueName, nodes, edges), [venueName, nodes, edges]);
  // Positions do not change the problem, so they are left out of the signature.
  const signature = useMemo(() => {
    if (!conversion.venue) return null;
    const { locations, ...rest } = conversion.venue;
    const places = locations.map((l) => ({ id: l.id, type: l.location_type, capacity: l.capacity }));
    return JSON.stringify({ ...rest, locations: places, settings });
  }, [conversion, settings]);

  // Fetch the formulation summary (qubit count, validation) whenever the problem changes.
  useEffect(() => {
    if (!signature || !conversion.venue) return;
    const venue = conversion.venue, sig = signature;
    const t = setTimeout(() => {
      api.problem(venue, settings)
        .then((s) => setProblem({ sig, summary: s, error: null }))
        .catch((e) => setProblem({ sig, summary: null, error: e.message }));
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  const current = results.sig != null && results.sig === signature;
  const runs: Runs = current ? results.runs : {};
  const shown: Shown = current ? results.shown : null;
  const runError = current ? results.error : null;
  const summary = problem.sig === signature ? problem.summary : null;
  const problemError = problem.sig === signature ? problem.error : null;
  const setShown = (k: Shown) => setResults((r) => ({ ...r, shown: k }));

  // ------------------------------------------------------------ editing
  const selectedNode = nodes.find((n) => n.selected) ?? null;
  const selectedEdge = selectedNode ? null : edges.find((e) => e.selected) ?? null;
  const nameOf = (id: string) => nodes.find((n) => n.id === id)?.data.name ?? "?";

  const addPlace = (exit: boolean) => {
    const count = nodes.filter((n) => (n.data.locationType === "exit") === exit).length + 1;
    const xs = nodes.map((n) => n.position.x), ys = nodes.map((n) => n.position.y);
    const x = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 300;
    const y = ys.length ? Math.max(...ys) + 90 : 200;
    setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), {
      id: newId("n"), type: exit ? "exit" : "place", position: { x: x + (count % 3) * 40, y }, selected: true,
      data: exit
        ? { name: `Exit ${count}`, locationType: "exit", capacity: 300, people: 0 }
        : { name: `Area ${count}`, locationType: "zone", capacity: null, people: 100 },
    }]);
  };

  const updateNode = (id: string, patch: Partial<PlaceNode["data"]>) => {
    setNodes((ns) => ns.map((n) => {
      if (n.id !== id) return n;
      const data = { ...n.data, ...patch };
      if (patch.locationType) {
        const exit = patch.locationType === "exit";
        if (exit) { data.people = 0; data.capacity = data.capacity ?? 300; }
        return { ...n, type: exit ? "exit" : "place", data };
      }
      return { ...n, data };
    }));
  };

  const updateEdge = (id: string, patch: Partial<NonNullable<RouteEdge["data"]>>) =>
    setEdges((es) => es.map((e) => (e.id === id ? { ...e, data: { ...e.data!, ...patch } } : e)));

  const deleteSelected = () => {
    const gone = new Set(nodes.filter((n) => n.selected).map((n) => n.id));
    setNodes((ns) => ns.filter((n) => !n.selected));
    setEdges((es) => es.filter((e) => !e.selected && !gone.has(e.source) && !gone.has(e.target)));
  };

  const onConnect = (c: Connection) => {
    if (!c.source || !c.target || c.source === c.target) return;
    const exists = edges.some((e) => (e.source === c.source && e.target === c.target) || (e.source === c.target && e.target === c.source));
    if (exists) return;
    setEdges((es) => [...es, { id: newId("e"), type: "route", source: c.source!, target: c.target!, data: { capacity: 200, length: 15 } }]);
  };

  // ------------------------------------------------------------ solving
  const qubits = summary?.num_qubits ?? null;
  const blocked = apiError ?? (conversion.errors.length ? conversion.errors[0] : problemError);

  const run = async (key: SolverKey) => {
    if (!conversion.venue || !signature) return;
    const sig = signature;
    setRunning(key);
    setResults((r) => (r.sig === sig ? { ...r, error: null } : { sig, runs: {}, shown: null, error: null }));
    try {
      const isQuantum = SOLVERS.find((s) => s.key === key)!.quantum;
      const resp = await api.optimize(conversion.venue, settings, key, isQuantum ? quantum : undefined);
      if (key === "qaoa_noisy") {
        setNoiseLabel(quantum.noise === "depolarizing"
          ? `${quantum.noise_level}x errors`
          : DEVICE_MODELS.find((d) => d.value === quantum.fake_backend)?.label.split(" (")[0] ?? quantum.fake_backend);
      }
      setResults((r) => r.sig === sig ? { ...r, runs: { ...r.runs, [key]: resp }, shown: key } : r);
    } catch (e) {
      setResults((r) => (r.sig === sig ? { ...r, error: (e as Error).message } : r));
    } finally {
      setRunning(null);
    }
  };

  const runAll = async () => {
    for (const k of ["classical_exact", "qaoa_ideal", "qaoa_noisy"] as SolverKey[]) {
      if (k !== "classical_exact" && qubits != null && qubits > QUANTUM_QUBIT_LIMIT) continue;
      await run(k);
    }
  };

  const anyRun = SOLVERS.map((s) => s.key).find((k) => runs[k]);
  const shownResult = shown === "baseline" ? (anyRun ? runs[anyRun]!.baseline : null) : shown ? runs[shown]?.result ?? null : null;
  const loads = useMemo(() => (shownResult ? planLoads(shownResult.evaluation, conversion.routeIds) : null),
    [shownResult, conversion.routeIds]);
  const shownLabel = shown === "baseline" ? "Nearest exit plan" : shown ? `${SOLVERS.find((s) => s.key === shown)!.label} plan` : "";

  return (
    <main className="mx-auto max-w-[1440px] space-y-5 px-5 py-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-bold">Venue lab</h1>
          <p className="max-w-[70ch] text-sm text-ink-soft">
            Build or load a venue, then route its crowd to the exits with a classical solver and with QAOA.
          </p>
        </div>
        <div className="num rounded-[3px] border border-line bg-panel px-3 py-1.5 text-sm">
          {qubits != null
            ? <><b>{qubits}</b> qubits, {summary!.num_groups} crowd groups</>
            : <span className="text-ink-soft">Venue incomplete</span>}
        </div>
      </div>

      {apiError && <p className="rounded-[3px] border border-wine/40 bg-white px-4 py-3 text-sm text-wine">{apiError}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-56">
          <Select<string> value={presetId}
            onChange={(v) => { setPresetId(v); loadPreset(v); }}
            options={presets.length ? presets.map((p) => ({ value: p.id, label: `${p.name} (${p.num_qubits} qubits)` }))
              : [{ value: presetId, label: "Loading venues…" }]} />
        </div>
        <div className="w-56"><TextInput aria-label="Venue name" value={venueName} onChange={(e) => setVenueName(e.target.value)} /></div>
        <span className="mx-1 h-6 w-px bg-line" />
        <Button onClick={() => addPlace(false)}>Add area</Button>
        <Button onClick={() => addPlace(true)}>Add exit</Button>
        <Button variant="ghost" onClick={() => loadPreset(presetId)}>Reset venue</Button>
        <Button variant="ghost" onClick={() => { setNodes([]); setEdges([]); setVenueName("My venue"); }}>Start blank</Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div>
        <div className="relative h-[620px] overflow-hidden rounded-[4px] border border-line bg-white">
          <VenueCanvas key={canvasKey} className="h-full w-full" editable nodes={nodes} edges={edges} loads={loads}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} />
          {anyRun && (
            <div className="absolute left-3 top-3 flex flex-wrap gap-1 rounded-[3px] border border-line bg-white/95 p-1" role="group" aria-label="Plan shown on the map">
              {(["baseline", ...SOLVERS.map((s) => s.key).filter((k) => runs[k])] as Exclude<Shown, null>[]).map((k) => (
                <button key={k} onClick={() => setShown(k)}
                  className={`rounded-[2px] px-2.5 py-1 text-[13px] ${shown === k ? "bg-ink text-white" : "text-ink-soft hover:text-ink"}`}>
                  {k === "baseline" ? "Nearest exit" : SOLVERS.find((s) => s.key === k)!.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <LoadLegend className="mt-2" />
        </div>

        <aside className="space-y-5">
          <section className="rounded-[4px] border border-line bg-panel p-4">
            <Inspector node={selectedNode} edge={selectedEdge} nodeName={nameOf}
              onNodeChange={updateNode} onEdgeChange={updateEdge} onDelete={deleteSelected} />
          </section>
          <section className="rounded-[4px] border border-line bg-panel p-4">
            <SolverPanel selected={solver} onSelect={setSolver} settings={settings} onSettings={setSettings}
              quantum={quantum} onQuantum={setQuantum} qubits={qubits} blocked={blocked} running={running}
              onRun={run} onRunAll={runAll} />
          </section>
        </aside>
      </div>

      {runError && <p className="rounded-[3px] border border-wine/40 bg-white px-4 py-3 text-sm text-wine">{runError}</p>}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <ResultsBoard runs={runs} noiseLabel={noiseLabel} />
        {shownResult && (
          <section className="rounded-[4px] border border-line bg-panel p-4">
            <PlanList title={shownLabel} plan={shownResult.routes}
              note={shown && SOLVERS.find((s) => s.key === shown)?.quantum ? "The best plan found among all shots." : undefined} />
          </section>
        )}
      </div>
    </main>
  );
}
