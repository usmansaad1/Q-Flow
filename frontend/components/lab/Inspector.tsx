"use client";
// WHAT THIS FILE IS FOR: the side panel for editing whatever is selected on the venue map.
// Pick an area, exit or route and its settings appear here to change or delete.
// The Lab page shows it next to the venue editor.

import { MAX_SPLIT, PLACE_TYPES, WALK_SPEED, splitCrowd, type PlaceNode, type RouteEdge } from "@/lib/venue";
import type { LocationType } from "@/lib/types";
import { Button, Field, NumberInput, OptionalNumberInput, Select, TextInput } from "./Field";

// What the panel is given: the selected place or route, plus ways to report changes back.
interface Props {
  node: PlaceNode | null;
  edge: RouteEdge | null;
  nodeName: (id: string) => string;
  onNodeChange: (id: string, patch: Partial<PlaceNode["data"]>) => void;
  onEdgeChange: (id: string, patch: Partial<NonNullable<RouteEdge["data"]>>) => void;
  // Makes the route one way in the opposite direction (swaps its start and end).
  onEdgeReverse: (id: string) => void;
  onDelete: () => void;
}

// Shows one of three forms: for a place, for a route, or a short help note when nothing is selected.
export default function Inspector({ node, edge, nodeName, onNodeChange, onEdgeChange, onEdgeReverse, onDelete }: Props) {
  // Case 1: a place (area or exit) is selected.
  if (node) {
    const d = node.data;
    const isExit = d.locationType === "exit";
    return (
      <div className="space-y-3">
        <h3 className="font-display text-base font-bold">{isExit ? "Exit" : "Area"}</h3>
        {/* The place's name and type; changing the type to exit turns it into a way out */}
        <Field label="Name">
          <TextInput value={d.name} onChange={(e) => onNodeChange(node.id, { name: e.target.value })} />
        </Field>
        <Field label="Type">
          <Select<LocationType> value={d.locationType} options={PLACE_TYPES}
            onChange={(v) => onNodeChange(node.id, { locationType: v })} />
        </Field>
        {/* Exits ask for capacity; ordinary areas ask for head count and how many groups to split into */}
        {isExit ? (
          <Field label="Exit capacity" hint="People this exit can take during the evacuation.">
            <NumberInput value={d.capacity ?? 0} min={1}
              onChange={(v) => onNodeChange(node.id, { capacity: v > 0 ? v : null })} />
          </Field>
        ) : (
          <>
            <Field label="People here">
              <NumberInput value={d.people} min={0} step={10} onChange={(v) => onNodeChange(node.id, { people: v })} />
            </Field>
            <Field label="Split into groups"
              hint={d.groups > 1
                ? `Groups of ${splitCrowd(d.name, d.people, d.groups).map((g) => g.size).join(", ")}. Each can take a different route. Adds qubits for quantum solvers.`
                : "Everyone here leaves together by one route. Split to let them use several routes; each extra group adds qubits."}>
              <Select<number> value={d.groups} onChange={(v) => onNodeChange(node.id, { groups: v })}
                options={Array.from({ length: MAX_SPLIT }, (_, i) => ({
                  value: i + 1, label: i === 0 ? "1 (move together)" : `${i + 1} groups`,
                }))} />
            </Field>
          </>
        )}
        <Button variant="danger" onClick={onDelete}>Delete {isExit ? "exit" : "area"}</Button>
      </div>
    );
  }
  // Case 2: a route between two places is selected.
  if (edge) {
    // The names of the two places this route joins, for the labels below.
    const a = nodeName(edge.source), b = nodeName(edge.target);
    return (
      <div className="space-y-3">
        <h3 className="font-display text-base font-bold">Route</h3>
        <p className="text-sm text-ink-soft">
          {edge.data!.oneWay ? <>One way from {a} to {b}.</> : <>Between {a} and {b}, usable both ways.</>}
        </p>
        {/* Direction: both ways, or one way in either direction. Choosing the reverse swaps the route's ends */}
        <Field label="Direction"
          hint="One way routes can only be walked in the direction of their arrows, like an exit only turnstile or a one way staircase.">
          <Select<"both" | "forward" | "reverse"> value={edge.data!.oneWay ? "forward" : "both"}
            onChange={(v) => {
              if (v === "both") onEdgeChange(edge.id, { oneWay: false });
              else if (v === "forward") onEdgeChange(edge.id, { oneWay: true });
              else onEdgeReverse(edge.id);
            }}
            options={[
              { value: "both", label: "Both ways" },
              { value: "forward", label: `One way: ${a} to ${b}` },
              { value: "reverse", label: `One way: ${b} to ${a}` },
            ]} />
        </Field>
        {/* Capacity, length and travel time. An empty travel time is guessed from the length */}
        <Field label="Capacity" hint="People this route can carry during the evacuation.">
          <NumberInput value={edge.data!.capacity} min={1} step={10}
            onChange={(v) => onEdgeChange(edge.id, { capacity: v })} />
        </Field>
        <Field label="Length (metres)">
          <NumberInput value={edge.data!.length} min={1} onChange={(v) => onEdgeChange(edge.id, { length: v })} />
        </Field>
        <Field label="Travel time (seconds)"
          hint={edge.data!.travelTime == null
            ? `Empty means estimated from length at walking pace: about ${Math.round(edge.data!.length / WALK_SPEED)} s.`
            : "Use this for stairs, ramps or slow routes. Clear it to go back to the estimate."}>
          <OptionalNumberInput value={edge.data!.travelTime} min={1} placeholder={`about ${Math.round(edge.data!.length / WALK_SPEED)}`}
            onChange={(v) => onEdgeChange(edge.id, { travelTime: v })} />
        </Field>
        <Button variant="danger" onClick={onDelete}>Delete route</Button>
      </div>
    );
  }
  // Case 3: nothing is selected, so explain how to start editing.
  return (
    <div className="space-y-2 text-sm text-ink-soft">
      <h3 className="font-display text-base font-bold text-ink">Edit the venue</h3>
      <p>Select an area, exit or route to change it. Drag the purple dot on an area onto another place to add a route.</p>
      <p>Press Delete to remove whatever is selected.</p>
    </div>
  );
}
