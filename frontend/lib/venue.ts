// WHAT THIS FILE IS FOR: converts a venue between the server's format and the drawing the user edits.
// The venue editor uses it to load a venue onto the canvas and to check and send it back.
// It also splits a crowd into smaller groups.
import type { Edge, Node } from "@xyflow/react";
import type { LocationType, VenueDTO } from "./types";

// The details shown on one box (a place or an exit) in the venue drawing.
/** Data carried by each node on the venue canvas. */
export type PlaceData = {
  name: string;
  locationType: LocationType;
  capacity: number | null; // exits only
  people: number;          // total people starting here (0 = none)
  groups: number;          // how many crowd groups those people are split into (1 = move together)
  load?: number;           // exit load in the plan being shown
  util?: number;
};

// Measured in metres per second.
/** Walking speed the backend uses to estimate travel time when none is given. */
export const WALK_SPEED = 1.3;

// The details shown on one line (a walkway) in the venue drawing.
export type RouteData = {
  capacity: number;
  length: number;
  travelTime: number | null; // seconds; null means "estimate from length"
  // True when people may only walk this route from its start box to its end box,
  // for example an exit only turnstile. False or missing means both ways.
  oneWay?: boolean;
  load?: number;
  util?: number;
};

// A box on the drawing (a place or an exit) and a line between two boxes (a route).
export type PlaceNode = Node<PlaceData, "place" | "exit">;
export type RouteEdge = Edge<RouteData, "route">;

// The kinds of place offered in the editor's menu, with friendly labels.
export const PLACE_TYPES: { value: LocationType; label: string }[] = [
  { value: "zone", label: "Zone" },
  { value: "hall", label: "Hall" },
  { value: "seating", label: "Seating" },
  { value: "event", label: "Event area" },
  { value: "corridor", label: "Corridor" },
  { value: "entrance", label: "Entrance" },
  { value: "exit", label: "Exit" },
];

// Makes a fresh unique id for a box or line, from the current time plus a running counter.
let counter = 0;
export const newId = (prefix: string) => `${prefix}_${Date.now().toString(36)}_${(counter++).toString(36)}`;

// Turns a venue from the server into boxes and lines for the drawing.
// Places without a saved position are laid out in a simple grid, four per row.
export function venueToGraph(v: VenueDTO): { nodes: PlaceNode[]; edges: RouteEdge[] } {
  // Step 1: add up the people and groups starting in each place.
  const people = new Map<string, number>();
  const groupCount = new Map<string, number>();
  v.crowd_groups.forEach((g) => {
    people.set(g.location, (people.get(g.location) ?? 0) + g.size);
    groupCount.set(g.location, (groupCount.get(g.location) ?? 0) + 1);
  });
  // Step 2: make one box per place, remembering which box belongs to which place name.
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
        groups: isExit ? 1 : groupCount.get(l.id) ?? 1,
      },
    };
  });
  // Step 3: make one line per route, joining the right two boxes.
  const edges: RouteEdge[] = v.routes.map((r) => ({
    id: newId("e"),
    type: "route",
    source: idByName.get(r.from_node)!,
    target: idByName.get(r.to_node)!,
    data: { capacity: r.capacity, length: r.length, travelTime: r.travel_time ?? null, oneWay: r.bidirectional === false },
  }));
  return { nodes, edges };
}

// The outcome of checking the drawing: the venue (if valid), any problems found, and a route lookup.
export interface GraphConversion {
  venue: VenueDTO | null;
  errors: string[];
  /** canvas edge id -> backend route resource id */
  routeIds: Map<string, string>;
}

// Reads the user's drawing back into a venue the server understands.
// If anything is wrong it returns a list of friendly problem messages instead of a venue.
/** Turn the canvas into the backend's venue format, with plain language validation. */
export function graphToVenue(name: string, nodes: PlaceNode[], edges: RouteEdge[]): GraphConversion {
  // Step 1: check names, exits and that at least one area has people.
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

  // Step 2: check every route for duplicates and sensible numbers, and record its server name.
  const routeIds = new Map<string, string>();
  const seen = new Set<string>();
  for (const e of edges) {
    const a = nameById.get(e.source)!, b = nameById.get(e.target)!;
    const key = [a, b].sort().join("|");
    if (seen.has(key)) errors.push(`There are two routes between ${a} and ${b}.`);
    seen.add(key);
    if (!(e.data!.capacity > 0) || !(e.data!.length > 0)) errors.push(`Route ${a} to ${b} needs a capacity and length above 0.`);
    if (e.data!.travelTime != null && !(e.data!.travelTime > 0)) errors.push(`Route ${a} to ${b} needs a travel time above 0, or leave it empty.`);
    routeIds.set(e.id, `${a}|${b}`);
  }
  // Step 3: check that every crowd can be split as asked and has a way out.
  for (const n of crowds) {
    if (n.data.groups > n.data.people) errors.push(`${n.data.name} can't be split into more groups than it has people.`);
    if (!edges.some((e) => e.source === n.id || e.target === n.id))
      errors.push(`${n.data.name} has people but no routes.`);
  }
  if (errors.length) return { venue: null, errors, routeIds };

  // Step 4: all checks passed, so build the venue: places, routes and crowd groups.
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
        travel_time: e.data!.travelTime ?? null,
        // A one way route can only be walked from its start box to its end box.
        bidirectional: !e.data!.oneWay,
      })),
      crowd_groups: crowds.flatMap((n) => splitCrowd(n.data.name.trim(), n.data.people, n.data.groups)),
    },
  };
}

// Kept small because each extra group adds qubits (the basic units of a quantum computer).
/** Maximum number of groups one area's crowd can be split into. */
export const MAX_SPLIT = 4;

/**
 * Split an area's crowd into near equal groups, each of which moves as one unit
 * and can take a different route. 301 people in 3 groups gives 101, 100, 100.
 * With one group the name stays "<area> crowd", so unsplit venues are unchanged.
 */
export function splitCrowd(area: string, people: number, groups: number) {
  const k = Math.max(1, Math.min(Math.floor(groups) || 1, MAX_SPLIT, people));
  const base = Math.floor(people / k), extra = people % k;
  return Array.from({ length: k }, (_, i) => ({
    group_id: k === 1 ? `${area} crowd` : `${area} crowd ${i + 1}`,
    location: area,
    size: base + (i < extra ? 1 : 0),
  }));
}
