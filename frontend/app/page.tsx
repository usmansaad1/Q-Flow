"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import LoadLegend from "@/components/LoadLegend";
import VenueCanvas from "@/components/VenueCanvas";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";
import { planLoads } from "@/lib/plan";
import type { OptimizeResponse } from "@/lib/types";
import { graphToVenue, venueToGraph, type PlaceNode, type RouteEdge } from "@/lib/venue";

const STEPS = [
  { title: "Model the venue", body: "Areas, corridors and exits become a graph. Every route and exit has a capacity." },
  { title: "Write it as a QUBO", body: "Each choice of route for a crowd group is one binary variable, so one qubit." },
  { title: "Solve it three ways", body: "Exactly with a classical solver, then with QAOA on a perfect simulator, a noisy one and real IBM hardware." },
  { title: "Measure the gap", body: "Compare answer quality, reliability and cost as problems grow and noise rises." },
];

export default function Home() {
  const [graph, setGraph] = useState<{ nodes: PlaceNode[]; edges: RouteEdge[] } | null>(null);
  const [resp, setResp] = useState<OptimizeResponse | null>(null);
  const [view, setView] = useState<"before" | "after">("before");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const v = await api.preset("concert_venue");
        setGraph(venueToGraph(v));
        setResp(await api.optimize(v, { weights: { distance: 1, time: 0, congestion: 1, overflow: 2 }, paths_per_group: 2, penalty_factor: 1.5 }, "classical_exact"));
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  const routeIds = useMemo(() => (graph ? graphToVenue("", graph.nodes, graph.edges).routeIds : new Map()), [graph]);
  const ev = resp ? (view === "before" ? resp.baseline : resp.result).evaluation : null;
  const loads = useMemo(() => (ev ? planLoads(ev, routeIds) : null), [ev, routeIds]);

  return (
    <main className="mx-auto max-w-[1440px] px-5 pb-16 pt-10">
      <div className="grid items-end gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <h1 className="max-w-[18ch] font-display text-[clamp(2.2rem,5vw,4rem)] font-bold leading-[1.02]">
          How close is quantum optimisation to routing a real crowd?
        </h1>
        <p className="text-sm text-ink-soft">
          Q-Flow sends each crowd group in a venue to an exit, then compares the best classical answer with what today&apos;s
          quantum algorithms can manage.
        </p>
      </div>

      <section className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <div className="h-[460px] overflow-hidden rounded-[4px] border border-line bg-white">
            {graph ? <VenueCanvas nodes={graph.nodes} edges={graph.edges} loads={loads} className="h-full w-full" />
              : <div className="grid h-full place-items-center p-8 text-center text-sm text-ink-soft">{error ?? "Loading the concert venue…"}</div>}
          </div>
          <LoadLegend className="mt-2" />
        </div>

        <div className="flex flex-col">
          <p className="text-sm text-ink-soft">Concert venue: 980 people, four crowd sections, three gates.</p>
          <div className="mt-3 inline-flex self-start rounded-[3px] border border-line bg-white p-1" role="group" aria-label="Plan shown">
            {(["before", "after"] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} disabled={!resp}
                className={`rounded-[2px] px-3 py-1.5 text-sm ${view === v ? "bg-ink text-white" : "text-ink-soft hover:text-ink"}`}>
                {v === "before" ? "Nearest gate" : "Optimised"}
              </button>
            ))}
          </div>
          {ev && (
            <dl className="mt-6 space-y-5">
              <div>
                <dt className="text-sm text-ink-soft">People over capacity</dt>
                <dd className={`num font-display text-5xl font-bold ${ev.people_over_capacity ? "text-wine" : "text-exit"}`}>
                  {ev.people_over_capacity}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-ink-soft">Busiest route or gate</dt>
                <dd className="num font-display text-3xl font-bold">{pct(ev.max_utilisation)} full</dd>
              </div>
            </dl>
          )}
          <p className="mt-auto pt-6 text-sm text-ink-soft">
            The optimised plan comes from the exact classical solver. Q-Flow asks how close QAOA gets to it.
          </p>
        </div>
      </section>

      <section className="mt-14 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="max-w-[60ch] space-y-4">
          <h2 className="font-display text-2xl font-bold">What this project tests</h2>
          <p>
            Q-Flow turns crowd routing into a binary optimisation problem and solves it both classically and with the
            Quantum Approximate Optimisation Algorithm, using IBM&apos;s Qiskit. The aim is not to show quantum winning. Classical
            methods are expected to stay ahead. The aim is to measure by how much, and how that gap moves with problem size,
            noise and circuit depth.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link href="/lab" className="rounded-[3px] bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-ink/90">Open the venue lab</Link>
            <Link href="/experiments" className="rounded-[3px] border border-line bg-white px-4 py-2 text-sm font-medium hover:border-ink/50">See the experiments</Link>
          </div>
        </div>
        <ol className="grid gap-x-8 gap-y-6 sm:grid-cols-2">
          {STEPS.map((s, i) => (
            <li key={s.title} className="border-t-2 border-ink pt-3">
              <span className="num font-display text-sm font-bold text-ink-soft">Step {i + 1}</span>
              <h3 className="font-display text-lg font-bold">{s.title}</h3>
              <p className="text-sm text-ink-soft">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
