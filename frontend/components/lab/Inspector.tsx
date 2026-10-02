"use client";

import { PLACE_TYPES, type PlaceNode, type RouteEdge } from "@/lib/venue";
import type { LocationType } from "@/lib/types";
import { Button, Field, NumberInput, Select, TextInput } from "./Field";

interface Props {
  node: PlaceNode | null;
  edge: RouteEdge | null;
  nodeName: (id: string) => string;
  onNodeChange: (id: string, patch: Partial<PlaceNode["data"]>) => void;
  onEdgeChange: (id: string, patch: Partial<NonNullable<RouteEdge["data"]>>) => void;
  onDelete: () => void;
}

export default function Inspector({ node, edge, nodeName, onNodeChange, onEdgeChange, onDelete }: Props) {
  if (node) {
    const d = node.data;
    const isExit = d.locationType === "exit";
    return (
      <div className="space-y-3">
        <h3 className="font-display text-base font-bold">{isExit ? "Exit" : "Area"}</h3>
        <Field label="Name">
          <TextInput value={d.name} onChange={(e) => onNodeChange(node.id, { name: e.target.value })} />
        </Field>
        <Field label="Type">
          <Select<LocationType> value={d.locationType} options={PLACE_TYPES}
            onChange={(v) => onNodeChange(node.id, { locationType: v })} />
        </Field>
        {isExit ? (
          <Field label="Exit capacity" hint="People this exit can take during the evacuation.">
            <NumberInput value={d.capacity ?? 0} min={1}
              onChange={(v) => onNodeChange(node.id, { capacity: v > 0 ? v : null })} />
          </Field>
        ) : (
          <Field label="People here" hint="They leave together as one crowd group. Each group adds qubits.">
            <NumberInput value={d.people} min={0} step={10} onChange={(v) => onNodeChange(node.id, { people: v })} />
          </Field>
        )}
        <Button variant="danger" onClick={onDelete}>Delete {isExit ? "exit" : "area"}</Button>
      </div>
    );
  }
  if (edge) {
    return (
      <div className="space-y-3">
        <h3 className="font-display text-base font-bold">Route</h3>
        <p className="text-sm text-ink-soft">{nodeName(edge.source)} to {nodeName(edge.target)}, usable both ways.</p>
        <Field label="Capacity" hint="People this route can carry during the evacuation.">
          <NumberInput value={edge.data!.capacity} min={1} step={10}
            onChange={(v) => onEdgeChange(edge.id, { capacity: v })} />
        </Field>
        <Field label="Length (metres)">
          <NumberInput value={edge.data!.length} min={1} onChange={(v) => onEdgeChange(edge.id, { length: v })} />
        </Field>
        <Button variant="danger" onClick={onDelete}>Delete route</Button>
      </div>
    );
  }
  return (
    <div className="space-y-2 text-sm text-ink-soft">
      <h3 className="font-display text-base font-bold text-ink">Edit the venue</h3>
      <p>Select an area, exit or route to change it. Drag the purple dot on an area onto another place to add a route.</p>
      <p>Press Delete to remove whatever is selected.</p>
    </div>
  );
}
