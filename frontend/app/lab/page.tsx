"use client";
// WHAT THIS FILE IS FOR: the Venue Lab page, the main workbench of the website.
// Users build or load a venue map, choose a solver (classical, quantum simulator or real IBM machine),
// run it, and compare how each one routes the crowd to the exits.
// This file holds all the page's memory and actions; the panels it uses only display and report back.

import { useEdgesState, useNodesState, type Connection } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import LoadLegend from "@/components/LoadLegend";
import VenueCanvas from "@/components/VenueCanvas";
import Inspector from "@/components/lab/Inspector";
import PlanList from "@/components/lab/PlanList";
import ResultsBoard from "@/components/lab/ResultsBoard";
import { Button } from "@/components/lab/Field";
import SolverPanel from "@/components/lab/SolverPanel";
import { useConfirm } from "@/components/ConfirmDialog";
import VenueBar, { type VenueSource } from "@/components/lab/VenueBar";
import RunHistory from "@/components/lab/RunHistory";
import { QUANTUM_QUBIT_LIMIT, SOLVERS, type SolverKey } from "@/components/lab/solvers";
import { api } from "@/lib/api";
import { planLoads } from "@/lib/plan";
import type {
  HardwareCheck, HardwareDevice, HardwareJobState, LabRunSummary, OptimizeResponse, PresetInfo, ProblemSettings,
  ProblemSummary, QuantumSettings, SavedVenueSummary, VenueDTO,
} from "@/lib/types";
import { graphToVenue, newId, venueToGraph, type PlaceNode, type RouteEdge } from "@/lib/venue";

// Starting priorities for a new problem: care most about overflowing capacity, then distance and congestion.
// Two possible routes are considered for each crowd group. The penalty factor sets how strongly
// rule breaking plans (such as a group given two routes) are punished in the score.
const DEFAULT_SETTINGS: ProblemSettings = {
  weights: { distance: 1, time: 0, congestion: 1, overflow: 2 },
  paths_per_group: 2,
  penalty_factor: 1.5,
};
// Starting quantum settings: 2 layers, 4096 shots (repeat readings), and the simple error dial at 1x.
// IBM Torino is the device copied if the user switches to a real device model. The fixed seed makes runs repeatable.
const DEFAULT_QUANTUM: QuantumSettings = {
  reps: 2, shots: 4096, noise: "depolarizing", noise_level: 1, fake_backend: "FakeTorino", seed: 7,
};

// The latest result from each solver, looked up by solver name.
type Runs = Partial<Record<SolverKey, OptimizeResponse>>;
// Which plan is currently painted on the map: the nearest exit plan, a solver's plan, or none.
type Shown = "baseline" | SolverKey | null;

// The whole Lab page. It remembers the venue, settings and results, and wires up every button.
export default function LabPage() {
  // Venue memory: the lists of example and saved venues, where the current one came from,
  // and its save state, name, boxes (nodes) and routes (edges).
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [savedList, setSavedList] = useState<SavedVenueSummary[]>([]);
  const [source, setSource] = useState<VenueSource>({ kind: "preset", id: "small_event_hall" });
  // Exact snapshot (layout included) of the venue as last loaded or saved, to detect unsaved edits.
  const [cleanSnapshot, setCleanSnapshot] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [venueName, setVenueName] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<PlaceNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<RouteEdge>([]);
  // A counter bumped on every load, which forces the map to redraw and refit from scratch.
  const [canvasKey, setCanvasKey] = useState(0);
  // Solving memory: priorities, quantum settings and the chosen solver.
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [quantum, setQuantum] = useState(DEFAULT_QUANTUM);
  const [solver, setSolver] = useState<SolverKey>("classical_exact");
  // Results remember which venue and settings they were computed for (sig);
  // anything computed for a different signature is treated as stale.
  const [results, setResults] = useState<{ sig: string | null; runs: Runs; shown: Shown; error: string | null }>(
    { sig: null, runs: {}, shown: null, error: null });
  // Which solver is busy right now, and whether the map shows the best quantum answer or the most common one.
  const [running, setRunning] = useState<SolverKey | null>(null);
  const [bestOfShots, setBestOfShots] = useState(false);
  // The server's summary of the problem (such as its qubit count), tagged with the venue it describes.
  const [problem, setProblem] = useState<{ sig: string | null; summary: ProblemSummary | null; error: string | null }>(
    { sig: null, summary: null, error: null });
  // A message shown when the server (the API, the back end program the page talks to) cannot be reached.
  const [apiError, setApiError] = useState<string | null>(null);
  // IBM hardware state. Checks and devices are per venue or per session; a check only counts for the venue it was made for.
  const [hwDevices, setHwDevices] = useState<HardwareDevice[]>([]);
  const [hwLoadError, setHwLoadError] = useState<string | null>(null);
  const [hwDevice, setHwDevice] = useState("auto");
  const [hwCheck, setHwCheck] = useState<{ sig: string; data: HardwareCheck } | null>(null);
  const [hwChecking, setHwChecking] = useState(false);
  const [hwStatus, setHwStatus] = useState<HardwareJobState | null>(null);

  // ------------------------------------------------------------ loading
  // Puts a venue onto the map: turns it into boxes and lines, sets its name and source,
  // and records a clean copy so later edits can be spotted.
  const applyVenue = useCallback((v: VenueDTO, src: VenueSource) => {
    const g = venueToGraph(v);
    setNodes(g.nodes);
    setEdges(g.edges);
    setVenueName(v.name);
    setCanvasKey((k) => k + 1);
    setSource(src);
    setCleanSnapshot(snapshotOf(v.name, g.nodes, g.edges));
    setApiError(null);
  }, [setNodes, setEdges]);

  // Reloads the list of the user's saved venues. Failures are quietly ignored.
  const refreshSaved = () => api.savedVenues().then(setSavedList).catch(() => {});

  // When the page first opens: fetch the example venues, the saved venues,
  // and load the "small event hall" example onto the map.
  // The "alive" flag stops updates if the user has already left the page.
  useEffect(() => {
    let alive = true;
    Promise.all([api.presets(), api.preset("small_event_hall"), api.savedVenues()])
      .then(([p, v, sv]) => {
        if (!alive) return;
        setPresets(p);
        setSavedList(sv);
        applyVenue(v, { kind: "preset", id: "small_event_hall" });
      })
      .catch((e) => { if (alive) setApiError(e.message); });
    return () => { alive = false; };
  }, [applyVenue]);

  // ---------------------------------------------- venue -> backend format
  // Converts the map into the format the server expects, or a list of reasons it is incomplete.
  const conversion = useMemo(() => graphToVenue(venueName, nodes, edges), [venueName, nodes, edges]);
  // A fingerprint of the venue plus settings, used to tell if saved results still match what is on screen.
  // Positions do not change the problem, so they are left out of the signature.
  const signature = useMemo(() => {
    if (!conversion.venue) return null;
    const { locations, ...rest } = conversion.venue;
    const places = locations.map((l) => ({ id: l.id, type: l.location_type, capacity: l.capacity }));
    return JSON.stringify({ ...rest, locations: places, settings });
  }, [conversion, settings]);

  // ---------------------------------------------------- saving and files
  // Compares the venue now with the clean copy to work out the save status and whether Save is allowed.
  const snapshot = useMemo(() => snapshotOf(venueName, nodes, edges), [venueName, nodes, edges]);
  const edited = snapshot !== cleanSnapshot;
  const status = source.kind === "saved" ? (edited ? "unsaved" : "saved")
    : source.kind === "preset" ? (edited ? "edited preset" : "unchanged preset") : "new";
  const saveBlockedReason = conversion.venue ? null : conversion.errors[0] ?? "The venue is incomplete.";
  const canSave = !saveBlockedReason && (source.kind !== "saved" || edited);

  // Shows a short message under the toolbar. Success messages fade after 3 seconds; errors stay.
  const flash = (kind: "ok" | "error", text: string) => {
    setNotice({ kind, text });
    if (kind === "ok") setTimeout(() => setNotice((n) => (n?.text === text ? null : n)), 3000);
  };

  // A yes or no pop up box, used before anything that could lose work.
  const [ask, confirmDialog] = useConfirm();
  // Asks "discard unsaved changes?" only when there is something to lose; otherwise says yes at once.
  const confirmDiscard = async () =>
    !edited || source.kind === "new" && nodes.length === 0 || ask({
      title: "Discard unsaved changes?",
      message: "Your changes to this venue haven't been saved and will be lost.",
      confirmLabel: "Discard changes", danger: true,
    });

  // Avoids duplicate venue names by adding "(2)", "(3)" and so on when a name is taken.
  const uniqueName = (base: string) => {
    const taken = new Set([...savedList.map((v) => v.name), ...presets.map((p) => p.name)]);
    if (!taken.has(base)) return base;
    for (let i = 2; ; i++) if (!taken.has(`${base} (${i})`)) return `${base} (${i})`;
  };

  // Saves the venue on the server as a brand new entry, then switches to editing that saved copy.
  const saveNew = async () => {
    if (!conversion.venue) return;
    const name = uniqueName(venueName.trim() || "My venue");
    setSaving(true);
    try {
      const summary = await api.saveVenue({ ...conversion.venue, name });
      setVenueName(name);
      setSource({ kind: "saved", id: summary.id });
      setCleanSnapshot(snapshotOf(name, nodes, edges));
      await refreshSaved();
      flash("ok", `Saved as "${name}".`);
    } catch (e) {
      flash("error", (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  // The main Save button: updates a saved venue in place, or saves anything else as new.
  const save = async () => {
    if (!conversion.venue) return;
    if (source.kind !== "saved") return saveNew();
    setSaving(true);
    try {
      await api.updateVenue(source.id, conversion.venue);
      setCleanSnapshot(snapshot);
      await refreshSaved();
      flash("ok", "Changes saved.");
    } catch (e) {
      flash("error", (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  // Loads a venue without asking; pick and reset ask first.
  const load = (src: VenueSource) => {
    if (src.kind === "preset") api.preset(src.id).then((v) => applyVenue(v, src)).catch((e) => setApiError(e.message));
    else if (src.kind === "saved") api.savedVenue(src.id).then((v) => applyVenue(v, src)).catch((e) => flash("error", e.message));
  };

  // Switches to another venue from the drop down, after checking for unsaved changes.
  const pick = async (src: VenueSource) => {
    if (await confirmDiscard()) load(src);
  };

  // Throws away edits by reloading the current venue as it was last loaded.
  const reset = async () => { if (source.kind !== "new" && await confirmDiscard()) load(source); };

  // Clears the map to start a new venue called "My venue".
  const blank = async () => {
    if (!(await confirmDiscard())) return;
    setNodes([]);
    setEdges([]);
    setVenueName("My venue");
    setSource({ kind: "new" });
    setCleanSnapshot(snapshotOf("My venue", [], []));
  };

  // Deletes the current saved venue from the server after confirming. The map itself stays on screen.
  const removeSaved = async () => {
    if (source.kind !== "saved") return;
    const ok = await ask({
      title: `Delete "${venueName}"?`,
      message: "The saved venue will be removed from your venues. This can't be undone.",
      confirmLabel: "Delete venue", danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteVenue(source.id);
      setSource({ kind: "new" });
      setCleanSnapshot(null);
      await refreshSaved();
      flash("ok", "Saved venue deleted. It's still on the canvas until you leave or load another.");
    } catch (e) {
      flash("error", (e as Error).message);
    }
  };

  // Downloads the venue as a file ending in ".qflow.json" so it can be shared or opened later.
  // JSON is a plain text format for storing structured data.
  const exportFile = () => {
    if (!conversion.venue) return;
    const slug = (venueName.trim() || "venue").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    const url = URL.createObjectURL(new Blob([JSON.stringify(conversion.venue, null, 2)], { type: "application/json" }));
    Object.assign(document.createElement("a"), { href: url, download: `${slug || "venue"}.qflow.json` }).click();
    URL.revokeObjectURL(url);
  };

  // Opens a venue file from the user's computer, checks it looks like a Q-Flow venue, and loads it unsaved.
  const importFile = async (file: File) => {
    if (!(await confirmDiscard())) return;
    try {
      const v = JSON.parse(await file.text()) as VenueDTO;
      if (!Array.isArray(v?.locations) || !Array.isArray(v?.routes) || !Array.isArray(v?.crowd_groups))
        throw new Error("This file doesn't look like a Q-Flow venue.");
      applyVenue({ ...v, name: v.name || file.name.replace(/\.(qflow\.)?json$/i, "") }, { kind: "new" });
      setCleanSnapshot(null);
      flash("ok", `Opened "${v.name || file.name}". Save it to keep it in your venues.`);
    } catch (e) {
      flash("error", e instanceof SyntaxError ? "That file isn't valid JSON." : (e as Error).message);
    }
  };

  // It waits about a third of a second after the last edit, so typing does not flood the server.
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

  // Only use results and problem facts that match the venue as it is now; older ones are hidden.
  const current = results.sig != null && results.sig === signature;
  const runs: Runs = current ? results.runs : {};
  const shown: Shown = current ? results.shown : null;
  const runError = current ? results.error : null;
  const summary = problem.sig === signature ? problem.summary : null;
  const problemError = problem.sig === signature ? problem.error : null;
  // Chooses which plan to paint on the map.
  const setShown = (k: Shown) => setResults((r) => ({ ...r, shown: k }));

  // ------------------------------------------------------------ editing
  // What is selected on the map (a place wins over a route), and a helper to look up a place's name.
  const selectedNode = nodes.find((n) => n.selected) ?? null;
  const selectedEdge = selectedNode ? null : edges.find((e) => e.selected) ?? null;
  const nameOf = (id: string) => nodes.find((n) => n.id === id)?.data.name ?? "?";

  // Adds a new area (100 people) or exit (capacity 300) just below the existing boxes, and selects it.
  const addPlace = (exit: boolean) => {
    const count = nodes.filter((n) => (n.data.locationType === "exit") === exit).length + 1;
    const xs = nodes.map((n) => n.position.x), ys = nodes.map((n) => n.position.y);
    const x = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 300;
    const y = ys.length ? Math.max(...ys) + 90 : 200;
    setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), {
      id: newId("n"), type: exit ? "exit" : "place", position: { x: x + (count % 3) * 40, y }, selected: true,
      data: exit
        ? { name: `Exit ${count}`, locationType: "exit", capacity: 300, people: 0, groups: 1 }
        : { name: `Area ${count}`, locationType: "zone", capacity: null, people: 100, groups: 1 },
    }]);
  };

  // Changes details of one place. Turning a place into an exit empties it of people and gives it a capacity.
  const updateNode = (id: string, patch: Partial<PlaceNode["data"]>) => {
    setNodes((ns) => ns.map((n) => {
      if (n.id !== id) return n;
      const data = { ...n.data, ...patch };
      if (patch.locationType) {
        const exit = patch.locationType === "exit";
        if (exit) { data.people = 0; data.groups = 1; data.capacity = data.capacity ?? 300; }
        return { ...n, type: exit ? "exit" : "place", data };
      }
      return { ...n, data };
    }));
  };

  // Changes details of one route, such as its capacity or length.
  const updateEdge = (id: string, patch: Partial<NonNullable<RouteEdge["data"]>>) =>
    setEdges((es) => es.map((e) => (e.id === id ? { ...e, data: { ...e.data!, ...patch } } : e)));

  // Makes a route one way in the opposite direction, by swapping its start and end boxes.
  const reverseEdge = (id: string) =>
    setEdges((es) => es.map((e) => (e.id === id
      ? { ...e, source: e.target, target: e.source, data: { ...e.data!, oneWay: true } } : e)));

  // Deletes whatever is selected, plus any routes left dangling by a deleted place.
  const deleteSelected = () => {
    const gone = new Set(nodes.filter((n) => n.selected).map((n) => n.id));
    setNodes((ns) => ns.filter((n) => !n.selected));
    setEdges((es) => es.filter((e) => !e.selected && !gone.has(e.source) && !gone.has(e.target)));
  };

  // Called when the user drags a line between two places. Adds a new route unless one already
  // joins them in either direction. New routes start at capacity 200 and 15 metres long.
  const onConnect = (c: Connection) => {
    if (!c.source || !c.target || c.source === c.target) return;
    const exists = edges.some((e) => (e.source === c.source && e.target === c.target) || (e.source === c.target && e.target === c.source));
    if (exists) return;
    setEdges((es) => [...es, { id: newId("e"), type: "route", source: c.source!, target: c.target!, data: { capacity: 200, length: 15, travelTime: null } }]);
  };

  // ------------------------------------------------------------ solving
  // The problem size, and the first reason (if any) that running must be blocked.
  const qubits = summary?.num_qubits ?? null;
  const blocked = apiError ?? (conversion.errors.length ? conversion.errors[0] : problemError);

  // Waits the given number of milliseconds before carrying on.
  const sleep = (ms: number) => new Promise((done) => setTimeout(done, ms));

  // Devices for the picker, loaded when the IBM solver is selected.
  useEffect(() => {
    if (solver !== "ibm_hardware") return;
    let alive = true;
    api.hardwareDevices()
      .then((d) => { if (alive) { setHwDevices(d); setHwLoadError(null); } })
      .catch((e) => { if (alive) setHwLoadError((e as Error).message); });
    return () => { alive = false; };
  }, [solver]);

  // "Transpiles" means rewrites the quantum program into the steps that machine can actually perform.
  // Dry run: transpiles the circuit for the device and reports its size. Sends nothing to IBM.
  const checkHardware = async () => {
    if (!conversion.venue || !signature) return;
    const sig = signature, venue = conversion.venue;
    setHwChecking(true);
    try {
      const data = await api.hardwareDryRun(venue, settings, quantum, hwDevice === "auto" ? null : hwDevice);
      setHwCheck({ sig, data });
    } catch (e) {
      setResults((r) => (r.sig === sig ? { ...r, error: (e as Error).message } : r));
    } finally {
      setHwChecking(false);
    }
  };

  // IBM runs wait in a queue, so the job is submitted once and then checked every 3 seconds.
  const runOnHardware = async (sig: string, venue: VenueDTO) => {
    const sent = await api.hardwareSubmit(venue, settings, quantum, hwDevice === "auto" ? null : hwDevice);
    setHwStatus({ job_id: sent.job_id, status: "SUBMITTED", backend: sent.backend });
    // Keep asking IBM until the job finishes, fails or is cancelled.
    for (;;) {
      await sleep(3000);
      const job = await api.hardwareJob(sent.job_id);
      if (job.status === "DONE") {
        const resp = job as OptimizeResponse;
        setResults((r) => (r.sig === sig ? { ...r, runs: { ...r.runs, ibm_hardware: resp }, shown: "ibm_hardware" } : r));
        refreshHistory();
        return;
      }
      if (job.status === "ERROR" || job.status === "CANCELLED") {
        throw new Error(job.error ?? `IBM reported the job as ${job.status.toLowerCase()}.`);
      }
      setHwStatus(job);
    }
  };

  // Runs one solver on the current venue and stores its result, tagged with the venue fingerprint.
  // If the venue changed since the last results, older results are cleared first.
  // IBM hardware goes through the queue above; the others ask the server directly.
  const run = async (key: SolverKey) => {
    if (!conversion.venue || !signature) return;
    const sig = signature, venue = conversion.venue;
    setRunning(key);
    setResults((r) => (r.sig === sig ? { ...r, error: null } : { sig, runs: {}, shown: null, error: null }));
    try {
      if (key === "ibm_hardware") {
        await runOnHardware(sig, venue);
      } else {
        const isQuantum = SOLVERS.find((s) => s.key === key)!.quantum;
        const resp = await api.optimize(venue, settings, key, isQuantum ? quantum : undefined);
        setResults((r) => r.sig === sig ? { ...r, runs: { ...r.runs, [key]: resp }, shown: key } : r);
        refreshHistory();
      }
    } catch (e) {
      setResults((r) => (r.sig === sig ? { ...r, error: (e as Error).message } : r));
    } finally {
      setRunning(null);
      setHwStatus(null);
    }
  };

  // ------------------------------------------------------- saved lab runs
  // The list of past runs, plus a run waiting to be reattached after its venue loads.
  // The list is fetched once when the page opens and refreshed after each run.
  const [history, setHistory] = useState<LabRunSummary[]>([]);
  const pendingRestore = useRef<{ solver: SolverKey; resp: OptimizeResponse } | null>(null);
  const refreshHistory = () => api.labRuns().then(setHistory).catch(() => {});
  useEffect(() => { api.labRuns().then(setHistory).catch(() => {}); }, []);

  // Deletes one past run from the history after confirming.
  const deleteRun = async (id: number) => {
    const ok = await ask({
      title: `Delete run #${id}?`,
      message: "It will be removed from Run history. This can't be undone.",
      confirmLabel: "Delete run", danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteLabRun(id);
      refreshHistory();
    } catch (e) {
      flash("error", `Could not delete run #${id}: ${(e as Error).message}`);
    }
  };

  // Reopens a past run: restores its venue, priorities, solver and quantum settings.
  // The result itself is attached a moment later, once the venue has finished loading.
  const openRun = async (id: number) => {
    if (!(await confirmDiscard())) return;
    try {
      const r = await api.labRun(id);
      pendingRestore.current = { solver: r.solver as SolverKey, resp: r };
      setSettings(r.settings);
      // Quantum runs: put the side panel back to the settings that run used.
      const cfg = r.result.extra.config as Partial<QuantumSettings> | undefined;
      if (cfg) {
        setQuantum((q) => ({
          ...q,
          reps: cfg.reps ?? q.reps, shots: cfg.shots ?? q.shots, seed: cfg.seed ?? q.seed,
          ...(r.solver === "qaoa_noisy" ? {
            noise: cfg.noise ?? q.noise, noise_level: cfg.noise_level ?? q.noise_level, fake_backend: cfg.fake_backend ?? q.fake_backend,
          } : {}),
        }));
      }
      setSolver(r.solver as SolverKey);
      applyVenue(r.venue, { kind: "new" });
      flash("ok", `Opened run #${id}. Its results are shown below.`);
    } catch (e) {
      flash("error", (e as Error).message);
    }
  };

  // Once the reopened venue has settled, attach its stored result to it.
  useEffect(() => {
    const p = pendingRestore.current;
    if (!p || !signature) return;
    pendingRestore.current = null;
    setResults({ sig: signature, runs: { [p.solver]: p.resp }, shown: p.solver, error: null });
  }, [signature, canvasKey]); // canvasKey changes on every load, even of an identical venue

  // Runs classical, quantum simulator and noisy quantum one after another.
  // Quantum runs are skipped when the venue is too big for them. IBM hardware is never included.
  const runAll = async () => {
    for (const k of ["classical_exact", "qaoa_ideal", "qaoa_noisy"] as SolverKey[]) {
      if (k !== "classical_exact" && qubits != null && qubits > QUANTUM_QUBIT_LIMIT) continue;
      await run(k);
    }
  };

  // Works out which plan to paint on the map and its title and note.
  // For quantum results the user can flip between the most common answer and the best of all shots.
  // "loads" is how many people use each route and exit in that plan, used to colour the map.
  const anyRun = SOLVERS.map((s) => s.key).find((k) => runs[k]);
  const shownResp = shown && shown !== "baseline" ? runs[shown] : undefined;
  const typical = shownResp?.typical ?? null;
  const showTypical = !!typical && !bestOfShots;
  const shownResult = shown === "baseline" ? (anyRun ? runs[anyRun]!.baseline : null)
    : showTypical ? typical : shownResp?.result ?? null;
  const loads = useMemo(() => (shownResult ? planLoads(shownResult.evaluation, conversion.routeIds) : null),
    [shownResult, conversion.routeIds]);
  const shownLabel = shown === "baseline" ? "Nearest exit plan"
    : shown ? `${SOLVERS.find((s) => s.key === shown)!.label}: ${typical ? (showTypical ? "most common answer" : "best of all shots") : "plan"}` : "";
  const shownNote = !typical ? undefined : showTypical
    ? `Came up in ${(typical.probability * 100).toFixed(1)}% of shots. This is what a single quantum run would most often give.${typical.evaluation.feasible ? "" : " It breaks the one route per group rule."}`
    : "The single best answer among all shots. Quantum rarely gives this; see Chance of the best plan.";

  return (
    <main className="mx-auto max-w-[1440px] space-y-5 px-5 py-6">
      {/* Page title, with the problem size badge on the right */}
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

      {/* Warning if the server cannot be reached */}
      {apiError && <p className="rounded-[3px] border border-wine/40 bg-white px-4 py-3 text-sm text-wine">{apiError}</p>}

      {/* Venue toolbar, then any short success or error message */}
      <VenueBar presets={presets} saved={savedList} source={source} onPick={pick}
        name={venueName} onName={setVenueName} status={status} canSave={canSave}
        saveBlockedReason={saveBlockedReason} saving={saving} onSave={save} onSaveAsNew={saveNew}
        onAddArea={() => addPlace(false)} onAddExit={() => addPlace(true)}
        onReset={reset} onImport={importFile} onExport={exportFile} onDelete={removeSaved} />
      {notice && (
        <p role="status" className={`-mt-2 text-sm ${notice.kind === "ok" ? "text-exit" : "text-wine"}`}>{notice.text}</p>
      )}

      {/* Two independent columns: the left (map and results) never moves when the
          right hand controls grow, for example when "Optimisation priorities" opens. */}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-5">
          {/* The editable venue map, with plan buttons on top once something has run */}
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
                  {/* For quantum results: switch between the most common answer and the best of all shots */}
                  {typical && (
                    <span className="ml-1 flex gap-1 border-l border-line pl-2" role="group" aria-label="Which quantum answer">
                      {([false, true] as const).map((b) => (
                        <button key={String(b)} onClick={() => setBestOfShots(b)}
                          className={`rounded-[2px] px-2.5 py-1 text-[13px] ${bestOfShots === b ? "bg-quantum text-white" : "text-ink-soft hover:text-ink"}`}>
                          {b ? "Best of all shots" : "Most common answer"}
                        </button>
                      ))}
                    </span>
                  )}
                </div>
              )}
            </div>
            <LoadLegend className="mt-2" />
          </div>

          {/* Any run error, the comparison table, the written plan and the run history */}
          {runError && <p className="rounded-[3px] border border-wine/40 bg-white px-4 py-3 text-sm text-wine">{runError}</p>}

          <ResultsBoard runs={runs} />

          {shownResult && (
            <section className="rounded-[4px] border border-line bg-panel p-4">
              <PlanList title={shownLabel} plan={shownResult.routes} note={shownNote} />
            </section>
          )}

          <RunHistory runs={history} onOpen={openRun} onDelete={deleteRun} />
        </div>

        {/* Right hand column: new venue button, the editing panel and the solver panel */}
        <aside className="space-y-5">
          <Button variant="green" className="w-full py-2" onClick={blank}
            title="Clear the canvas and build a venue from scratch">
            New blank venue
          </Button>
          <section className="rounded-[4px] border border-line bg-panel p-4">
            <Inspector node={selectedNode} edge={selectedEdge} nodeName={nameOf}
              onNodeChange={updateNode} onEdgeChange={updateEdge} onEdgeReverse={reverseEdge} onDelete={deleteSelected} />
          </section>
          <section className="rounded-[4px] border border-line bg-panel p-4">
            <SolverPanel selected={solver} onSelect={setSolver} settings={settings} onSettings={setSettings}
              quantum={quantum} onQuantum={setQuantum} qubits={qubits} blocked={blocked} running={running}
              onRun={run} onRunAll={runAll}
              hw={{ devices: hwDevices, device: hwDevice, onDevice: setHwDevice,
                    check: hwCheck && hwCheck.sig === signature ? hwCheck.data : null, checking: hwChecking,
                    onCheck: checkHardware, status: hwStatus, error: hwLoadError }} />
          </section>
        </aside>
      </div>
      {/* The pop up confirmation box, hidden until needed */}
      {confirmDialog}
    </main>
  );
}

// Writes the venue's name, places (with rounded positions) and routes into one line of text.
// Two equal texts mean nothing has changed.
/** Exact snapshot of the venue including layout, used to detect unsaved edits. */
function snapshotOf(name: string, nodes: PlaceNode[], edges: RouteEdge[]): string {
  return JSON.stringify({
    name: name.trim(),
    nodes: nodes.map((n) => [n.id, Math.round(n.position.x), Math.round(n.position.y), n.data.name, n.data.locationType, n.data.capacity, n.data.people, n.data.groups]),
    edges: edges.map((e) => [e.id, e.source, e.target, e.data?.capacity, e.data?.length, e.data?.travelTime, !!e.data?.oneWay]),
  });
}
