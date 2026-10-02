"""
Venue model for Q-Flow.

A venue is a graph of locations (nodes) joined by routes (edges). Crowd groups
start at a location and must leave through an exit. Every route, and optionally
every exit, is a *resource* with a capacity. The optimisation layer decides which
candidate path each group takes so that resources are not overloaded.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
import itertools

import networkx as nx

LOCATION_TYPES = {"entrance", "zone", "hall", "corridor", "seating", "event", "exit"}
DEFAULT_WALK_SPEED = 1.3  # metres per second, used when a route has no travel_time


@dataclass
class Location:
    id: str
    location_type: str
    capacity: Optional[int] = None   # only meaningful for exits (people per evacuation)
    x: Optional[float] = None        # layout position for the frontend
    y: Optional[float] = None

    @property
    def is_exit(self) -> bool:
        return self.location_type == "exit"


@dataclass
class Route:
    from_node: str
    to_node: str
    capacity: int
    length: float
    travel_time: Optional[float] = None
    bidirectional: bool = True
    id: Optional[str] = None

    def __post_init__(self):
        if self.id is None:
            self.id = f"{self.from_node}|{self.to_node}"
        if self.travel_time is None:
            self.travel_time = self.length / DEFAULT_WALK_SPEED


@dataclass
class CrowdGroup:
    group_id: str
    location: str
    size: int


@dataclass
class PathOption:
    """One candidate way for a group to leave the venue."""
    nodes: list[str]
    route_ids: list[str]
    exit_id: str
    length: float
    travel_time: float

    def resources(self) -> list[str]:
        """Route resources plus the exit resource used by this path."""
        return list(self.route_ids) + [exit_resource_id(self.exit_id)]


def exit_resource_id(exit_id: str) -> str:
    return f"exit:{exit_id}"


@dataclass
class Venue:
    name: str
    locations: list[Location] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)
    crowd_groups: list[CrowdGroup] = field(default_factory=list)
    description: str = ""

    # ------------------------------------------------------------------ build
    def add_location(self, id: str, location_type: str, capacity: int | None = None,
                     x: float | None = None, y: float | None = None) -> "Venue":
        self.locations.append(Location(id, location_type, capacity, x, y))
        return self

    def add_route(self, from_node: str, to_node: str, capacity: int, length: float,
                  travel_time: float | None = None, bidirectional: bool = True) -> "Venue":
        self.routes.append(Route(from_node, to_node, capacity, length, travel_time, bidirectional))
        return self

    def add_group(self, group_id: str, location: str, size: int) -> "Venue":
        self.crowd_groups.append(CrowdGroup(group_id, location, size))
        return self

    # ------------------------------------------------------------- accessors
    @property
    def location_map(self) -> dict[str, Location]:
        return {loc.id: loc for loc in self.locations}

    @property
    def route_map(self) -> dict[str, Route]:
        return {r.id: r for r in self.routes}

    @property
    def exits(self) -> list[Location]:
        return [loc for loc in self.locations if loc.is_exit]

    @property
    def total_people(self) -> int:
        return sum(g.size for g in self.crowd_groups)

    # ------------------------------------------------------------ validation
    def validate(self) -> None:
        errors: list[str] = []
        ids = [loc.id for loc in self.locations]
        if len(ids) != len(set(ids)):
            errors.append("Location ids must be unique.")
        locs = self.location_map
        for loc in self.locations:
            if loc.location_type not in LOCATION_TYPES:
                errors.append(f"Location '{loc.id}' has unknown type '{loc.location_type}'.")
            if loc.capacity is not None and loc.capacity <= 0:
                errors.append(f"Location '{loc.id}' capacity must be positive.")
        if not self.exits:
            errors.append("Venue needs at least one exit.")
        route_ids = [r.id for r in self.routes]
        if len(route_ids) != len(set(route_ids)):
            errors.append("Duplicate routes between the same pair of locations.")
        for r in self.routes:
            if r.from_node not in locs or r.to_node not in locs:
                errors.append(f"Route '{r.id}' references an unknown location.")
            if r.capacity <= 0 or r.length <= 0:
                errors.append(f"Route '{r.id}' needs positive capacity and length.")
        gids = [g.group_id for g in self.crowd_groups]
        if len(gids) != len(set(gids)):
            errors.append("Crowd group ids must be unique.")
        for g in self.crowd_groups:
            if g.location not in locs:
                errors.append(f"Group '{g.group_id}' starts at unknown location '{g.location}'.")
            elif locs[g.location].is_exit:
                errors.append(f"Group '{g.group_id}' already starts at an exit.")
            if g.size <= 0:
                errors.append(f"Group '{g.group_id}' size must be positive.")
        if errors:
            raise ValueError(" ".join(errors))

    # ----------------------------------------------------------------- graph
    def graph(self) -> nx.DiGraph:
        """Directed graph; bidirectional routes become two arcs sharing one route id."""
        g = nx.DiGraph()
        for loc in self.locations:
            g.add_node(loc.id, type=loc.location_type)
        for r in self.routes:
            attrs = dict(route_id=r.id, length=r.length, travel_time=r.travel_time, capacity=r.capacity)
            g.add_edge(r.from_node, r.to_node, **attrs)
            if r.bidirectional:
                g.add_edge(r.to_node, r.from_node, **attrs)
        return g

    def candidate_paths(self, start: str, k: int | None = None, weight: str = "length") -> list[PathOption]:
        """
        Candidate exit paths for a group starting at `start`, shortest first.

        Diversity first: the shortest path to each reachable exit is taken, then
        further alternative paths fill up to `k`. Paths never pass *through* an exit.
        k = None means one path per reachable exit.
        """
        g = self.graph()
        exit_ids = {e.id for e in self.exits}
        # Paths may not traverse an exit, so drop arcs leaving exits.
        g.remove_edges_from([(u, v) for u, v in list(g.edges) if u in exit_ids])

        def to_option(nodes: list[str]) -> PathOption:
            arcs = list(zip(nodes[:-1], nodes[1:]))
            return PathOption(
                nodes=list(nodes),
                route_ids=[g[u][v]["route_id"] for u, v in arcs],
                exit_id=nodes[-1],
                length=sum(g[u][v]["length"] for u, v in arcs),
                travel_time=sum(g[u][v]["travel_time"] for u, v in arcs),
            )

        per_exit: list[PathOption] = []
        for ex in exit_ids:
            try:
                per_exit.append(to_option(nx.shortest_path(g, start, ex, weight=weight)))
            except nx.NetworkXNoPath:
                continue
        per_exit.sort(key=lambda p: (getattr(p, weight), p.exit_id))
        if k is None or k <= len(per_exit):
            return per_exit[: k] if k else per_exit

        # Need extra alternatives: walk globally shortest simple paths via a virtual sink.
        sink = "__SINK__"
        g.add_node(sink)
        for ex in exit_ids:
            g.add_edge(ex, sink, route_id=None, length=0.0, travel_time=0.0, capacity=0)
        chosen = list(per_exit)
        seen = {tuple(p.nodes) for p in chosen}
        for nodes in itertools.islice(nx.shortest_simple_paths(g, start, sink, weight=weight), 200):
            nodes = nodes[:-1]
            if tuple(nodes) in seen:
                continue
            chosen.append(to_option(nodes))
            seen.add(tuple(nodes))
            if len(chosen) >= k:
                break
        g.remove_node(sink)
        return chosen

    # --------------------------------------------------------- serialisation
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "locations": [asdict(l) for l in self.locations],
            "routes": [asdict(r) for r in self.routes],
            "crowd_groups": [asdict(g) for g in self.crowd_groups],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Venue":
        v = cls(name=d.get("name") or d.get("venue_name") or "Unnamed Venue",
                description=d.get("description", ""))
        for l in d.get("locations", []):
            v.locations.append(Location(**{k: l.get(k) for k in ("id", "location_type", "capacity", "x", "y")}))
        for r in d.get("routes", []):
            v.routes.append(Route(
                from_node=r["from_node"], to_node=r["to_node"], capacity=r["capacity"],
                length=r["length"], travel_time=r.get("travel_time"),
                bidirectional=r.get("bidirectional", True), id=r.get("id"),
            ))
        for gr in d.get("crowd_groups", []):
            v.crowd_groups.append(CrowdGroup(gr["group_id"], gr["location"], gr["size"]))
        return v
