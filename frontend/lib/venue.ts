import type { Edge, Node } from "@xyflow/react";
import type { LocationType, VenueDTO } from "./types";

/** Data carried by each node on the venue canvas. */
export type PlaceData = {
  name: string;
  locationType: LocationType;
  capacity: number | null; // exits only
  people: number;          // size of the crowd group starting here (0 = none)
  load?: number;           // exit load in the plan being shown
  util?: number;
};

export type RouteData = {
  capacity: number;
  length: number;
  load?: number;
  util?: number;
};

export type PlaceNode = Node<PlaceData, "place" | "exit">;
export type RouteEdge = Edge<RouteData, "route">;

export const PLACE_TYPES: { value: LocationType; label: string }[] = [
  { value: "zone", label: "Zone" },
  { value: "hall", label: "Hall" },
  { value: "seating", label: "Seating" },
  { value: "event", label: "Event area" },
  { value: "corridor", label: "Corridor" },
  { value: "entrance", label: "Entrance" },
  { value: "exit", label: "Exit" },
];

let counter = 0;
export const newId = (prefix: string) => `${prefix}_${Date.now().toString(36)}_${(counter++).toString(36)}`;

export function venueToGraph(v: VenueDTO): { nodes: PlaceNode[]; edges: RouteEdge[] } {
  const people = new Map<string, number>();
  v.crowd_groups.forEach((g) => people.set(g.location, (people.get(g.location) ?? 0) + g.size));
  const idByName = new Map<string, string>();
  const nodes: PlaceNode[] = v.locations.map((l, i) => {
    const id = newId("n");
    idByName.set(l.id, id);
    const isExit = l.location_type === "exit";
    return {
      id,
      type: isExit ? "exit" : "place",
      position: { x: l.x ?? 120 + (i % 4) * 180, y: l.y ?? 80 + Math.floor(i / 4) * 140 },
      data: {
        name: l.id, locationType: l.location_type, capacity: l.capacity ?? null,
        people: isExit ? 0 : people.get(l.id) ?? 0,
      },
    };
  });
  const edges: RouteEdge[] = v.routes.map((r) => ({
    id: newId("e"),
    type: "route",
    source: idByName.get(r.from_node)!,
    target: idByName.get(r.to_node)!,
    data: { capacity: r.capacity, length: r.length },
  }));
  return { nodes, edges };
}

export interface GraphConversion {
  venue: VenueDTO | null;
  errors: string[];
  /** canvas edge id -> backend route resource id */
  routeIds: Map<string, string>;
}

/** Turn the canvas into the backend's venue format, with plain language validation. */
export function graphToVenue(name: string, nodes: PlaceNode[], edges: RouteEdge[]): GraphConversion {
  const errors: string[] = [];
  const nameById = new Map(nodes.map((n) => [n.id, n.data.name.trim()]));
  const names = [...nameById.values()];
  if (names.some((n) => !n)) errors.push("Every area and exit needs a name.");
  const dupes = names.filter((n, i) => n && names.indexOf(n) !== i);
  if (dupes.length) errors.push(`Names must be unique: ${[...new Set(dupes)].join(", ")}.`);
  const exits = nodes.filter((n) => n.data.locationType === "exit");
  if (!exits.length) errors.push("Add at least one exit.");
  const crowds = nodes.filter((n) => n.data.locationType !== "exit" && n.data.people > 0);
  if (!crowds.length) errors.push("Put people in at least one area.");

  const routeIds = new Map<string, string>();
  const seen = new Set<string>();
  for (const e of edges) {
    const a = nameById.get(e.source)!, b = nameById.get(e.target)!;
    const key = [a, b].sort().join("|");
    if (seen.has(key)) errors.push(`There are two routes between ${a} and ${b}.`);
    seen.add(key);
    if (!(e.data!.capacity > 0) || !(e.data!.length > 0)) errors.push(`Route ${a} to ${b} needs a capacity and length above 0.`);
    routeIds.set(e.id, `${a}|${b}`);
  }
  for (const n of crowds) {
    if (!edges.some((e) => e.source === n.id || e.target === n.id))
      errors.push(`${n.data.name} has people but no routes.`);
  }
  if (errors.length) return { venue: null, errors, routeIds };

  return {
    errors,
    routeIds,
    venue: {
      name: name.trim() || "Custom venue",
      locations: nodes.map((n) => ({
        id: n.data.name.trim(),
        location_type: n.data.locationType,
        capacity: n.data.locationType === "exit" ? n.data.capacity : null,
        x: Math.round(n.position.x),
        y: Math.round(n.position.y),
      })),
      routes: edges.map((e) => ({
        from_node: nameById.get(e.source)!,
        to_node: nameById.get(e.target)!,
        capacity: e.data!.capacity,
        length: e.data!.length,
      })),
      crowd_groups: crowds.map((n) => ({ group_id: `${n.data.name.trim()} crowd`, location: n.data.name.trim(), size: n.data.people })),
    },
  };
}
