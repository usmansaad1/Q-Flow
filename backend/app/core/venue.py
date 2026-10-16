# WHAT THIS FILE IS FOR: describes a venue in a form the computer can work with.
# It holds the places (halls, corridors, exits), the routes between them and the crowds inside.
# It also finds the possible ways out for each crowd, which the scoring step then compares.
# Almost every other part of the backend starts from the Venue defined here.
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

# The kinds of place a venue may contain. Anything else is rejected when the venue is checked.
# The walking speed is used to guess travel time when only a route's length is known.
LOCATION_TYPES = {"entrance", "zone", "hall", "corridor", "seating", "event", "exit"}
DEFAULT_WALK_SPEED = 1.3  # metres per second, used when a route has no travel_time


# One place in the venue, such as a hall, a corridor or an exit.
# A dataclass is simply a labelled box of values; here it stores the place's name, type and map position.
@dataclass
class Location:
    id: str
    location_type: str
    capacity: Optional[int] = None   # only meaningful for exits (people per evacuation)
    x: Optional[float] = None        # layout position for the frontend
    y: Optional[float] = None

    # Answers yes or no: is this place a way out of the venue?
    @property
    def is_exit(self) -> bool:
        return self.location_type == "exit"


# A walkway joining two places, with how many people it can carry and how long it is.
# Routes are two way unless marked otherwise.
@dataclass
class Route:
    from_node: str
    to_node: str
    capacity: int
    length: float
    travel_time: Optional[float] = None
    bidirectional: bool = True
    id: Optional[str] = None

    # Gives the route an id built from its two ends, "From|To", for example "Hall|Lobby".
    # The website never sends an id, so in practice every route gets its id this way.
    def __post_init__(self):
        if self.id is None:
            self.id = f"{self.from_node}|{self.to_node}"

    # How many seconds it takes to walk this route.
    @property
    def effective_travel_time(self) -> float:
        """Travel time in seconds: the given value, or an estimate from length at walking speed.
        Kept separate so an estimate is never saved as if someone had typed it in."""
        return self.travel_time if self.travel_time is not None else self.length / DEFAULT_WALK_SPEED


# A crowd of people who start together in one place and must all leave together.
@dataclass
class CrowdGroup:
    group_id: str
    location: str
    size: int


# One possible escape route for a crowd: the places it passes, the exit it uses,
# and its total length and walking time.
@dataclass
class PathOption:
    """One candidate way for a group to leave the venue."""
    nodes: list[str]
    route_ids: list[str]
    exit_id: str
    length: float
    travel_time: float

    # Lists everything this escape route uses up space on: each walkway, then the exit door.
    # The scoring step adds up how many people use each of these.
    def resources(self) -> list[str]:
        """Route resources plus the exit resource used by this path."""
        return list(self.route_ids) + [exit_resource_id(self.exit_id)]


# Makes a label for an exit door, e.g. "exit:Gate 1", so it never clashes with a route's name.
def exit_resource_id(exit_id: str) -> str:
    return f"exit:{exit_id}"


# The whole venue: its name, all places, all routes and all crowds.
# It can check itself for mistakes, find escape routes and save or load itself.
@dataclass
class Venue:
    name: str
    locations: list[Location] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)
    crowd_groups: list[CrowdGroup] = field(default_factory=list)
    description: str = ""

    # ------------------------------------------------------------------ build
    # Adds a new place to the venue. Returns the venue so several additions can be chained.
    def add_location(self, id: str, location_type: str, capacity: int | None = None,
                     x: float | None = None, y: float | None = None) -> "Venue":
        self.locations.append(Location(id, location_type, capacity, x, y))
        return self

    # Adds a new walkway between two places.
    def add_route(self, from_node: str, to_node: str, capacity: int, length: float,
                  travel_time: float | None = None, bidirectional: bool = True) -> "Venue":
        self.routes.append(Route(from_node, to_node, capacity, length, travel_time, bidirectional))
        return self

    # Adds a new crowd standing at a given place.
    def add_group(self, group_id: str, location: str, size: int) -> "Venue":
        self.crowd_groups.append(CrowdGroup(group_id, location, size))
        return self

    # ------------------------------------------------------------- accessors
    # A quick lookup table: give it a place name, get back that place.
    @property
    def location_map(self) -> dict[str, Location]:
        return {loc.id: loc for loc in self.locations}

    # A quick lookup table: give it a route name, get back that route.
    @property
    def route_map(self) -> dict[str, Route]:
        return {r.id: r for r in self.routes}

    # All the places that are exits.
    @property
    def exits(self) -> list[Location]:
        return [loc for loc in self.locations if loc.is_exit]

    # The number of people in the venue, adding up every crowd.
    @property
    def total_people(self) -> int:
        return sum(g.size for g in self.crowd_groups)

    # ------------------------------------------------------------ validation
    # Checks the venue for mistakes before any work is done on it.
    # Every problem found is collected, then all are reported together in one error message.
    def validate(self) -> None:
        errors: list[str] = []
        # Step 1: every place needs a unique name, a known type and a sensible exit size.
        ids = [loc.id for loc in self.locations]
        if len(ids) != len(set(ids)):
            errors.append("Location ids must be unique.")
        locs = self.location_map
        for loc in self.locations:
            if loc.location_type not in LOCATION_TYPES:
                errors.append(f"Location '{loc.id}' has unknown type '{loc.location_type}'.")
            if loc.capacity is not None and loc.capacity <= 0:
                errors.append(f"Location '{loc.id}' capacity must be positive.")
        # Step 2: there must be at least one way out.
        if not self.exits:
            errors.append("Venue needs at least one exit.")
        # Step 3: no two routes may cover the same stretch in the same direction.
        # Each route occupies one direction, or both when it is two way. A route that
        # occupies a direction already taken is a duplicate, so a two way A to B and
        # any route B to A clash, while one way routes in opposite directions may coexist.
        taken: set[tuple[str, str]] = set()
        duplicate = False
        for r in self.routes:
            arcs = {(r.from_node, r.to_node)} | ({(r.to_node, r.from_node)} if r.bidirectional else set())
            duplicate = duplicate or bool(arcs & taken)
            taken |= arcs
        if duplicate:
            errors.append("Duplicate routes between the same pair of locations.")
        # Step 4: every route must join real places and have sensible size, length and time.
        for r in self.routes:
            if r.from_node not in locs or r.to_node not in locs:
                errors.append(f"Route '{r.id}' references an unknown location.")
            if r.capacity <= 0 or r.length <= 0:
                errors.append(f"Route '{r.id}' needs positive capacity and length.")
            if r.travel_time is not None and r.travel_time <= 0:
                errors.append(f"Route '{r.id}' travel time must be positive.")
        # Step 5: every crowd needs a unique name, a real starting place that is not an exit,
        # and at least one person.
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
        # Step 6: stop with a readable list of every problem, if there were any.
        if errors:
            raise ValueError(" ".join(errors))

    # ----------------------------------------------------------------- graph
    # Turns the venue into a network map (places as dots, routes as arrows) using the networkx library.
    # This map is what the route finding below searches through.
    def graph(self) -> nx.DiGraph:
        """Directed graph; bidirectional routes become two arcs sharing one route id."""
        g = nx.DiGraph()
        for loc in self.locations:
            g.add_node(loc.id, type=loc.location_type)
        for r in self.routes:
            attrs = dict(route_id=r.id, length=r.length, travel_time=r.effective_travel_time, capacity=r.capacity)
            g.add_edge(r.from_node, r.to_node, **attrs)
            if r.bidirectional:
                g.add_edge(r.to_node, r.from_node, **attrs)
        return g

    # Finds a short list of sensible escape routes for a crowd starting at one place.
    # These are the choices the optimiser later picks between, one per crowd.
    # More choices per crowd means a bigger puzzle, and more qubits on a quantum computer.
    # (A qubit is the basic memory unit of a quantum computer; here, one qubit per choice.)
    def candidate_paths(self, start: str, k: int | None = None, weight: str = "length",
                        loads: dict[str, int] | None = None, size: int = 0,
                        own: set[str] | None = None) -> list[PathOption]:
        """
        Candidate exit paths for a group starting at `start`, shortest first.

        Diversity first: the shortest path to each reachable exit is taken, then
        further alternative paths fill up to `k`. Paths never pass *through* an exit.
        k = None means one path per reachable exit.
        """
        # Step 1: build the network map and note which places are exits.
        g = self.graph()
        exit_ids = {e.id for e in self.exits}
        # Paths may not traverse an exit, so drop arcs leaving exits.
        g.remove_edges_from([(u, v) for u, v in list(g.edges) if u in exit_ids])

        # Helper: turns a list of places into a full escape route record,
        # adding up its length and walking time along the way.
        def to_option(nodes: list[str]) -> PathOption:
            arcs = list(zip(nodes[:-1], nodes[1:]))
            return PathOption(
                nodes=list(nodes),
                route_ids=[g[u][v]["route_id"] for u, v in arcs],
                exit_id=nodes[-1],
                length=sum(g[u][v]["length"] for u, v in arcs),
                travel_time=sum(g[u][v]["travel_time"] for u, v in arcs),
            )

        # Step 2: find the single shortest way to each exit that can be reached.
        # If that already gives enough choices, return them, shortest first.
        per_exit: list[PathOption] = []
        for ex in exit_ids:
            try:
                per_exit.append(to_option(nx.shortest_path(g, start, ex, weight=weight)))
            except nx.NetworkXNoPath:
                continue
        per_exit.sort(key=lambda p: (getattr(p, weight), p.exit_id))
        if not per_exit:
            return []  # no exit reachable; the caller explains this in plain words
        if k is None or k <= len(per_exit):
            return per_exit[: k] if k else per_exit

        # Step 3: we need more choices than there are exits, so collect extra detours.
        # A pretend "sink" joins all exits, so one search finds the next shortest ways to any exit.
        # Detours more than twice as long as the best route are ignored, and at most 200 are looked at.
        # Need extra alternatives: walk globally shortest simple paths via a virtual sink.
        sink = "__SINK__"
        g.add_node(sink)
        for ex in exit_ids:
            g.add_edge(ex, sink, route_id=None, length=0.0, travel_time=0.0, capacity=0)
        chosen = list(per_exit)
        seen = {tuple(p.nodes) for p in chosen}
        pool = []
        limit = 2 * getattr(per_exit[0], weight) if per_exit else float("inf")
        for nodes in itertools.islice(nx.shortest_simple_paths(g, start, sink, weight=weight), 200):
            nodes = nodes[:-1]
            if tuple(nodes) in seen:
                continue
            opt = to_option(nodes)
            if getattr(opt, weight) > limit:
                break  # paths come shortest first, so nothing later qualifies
            pool.append(opt)
        g.remove_node(sink)

        # Step 4: choose which detours to keep, favouring quieter ones.
        # Congestion aware choice of the extra routes: prefer detours that avoid roads and
        # exits other groups are expected to crowd, then shorter ones. Without loads this
        # is simply "next shortest". The number of routes, and so of qubits, is unchanged.
        caps = {r.id: r.capacity for r in self.routes}
        caps.update({exit_resource_id(e.id): e.capacity for e in self.exits if e.capacity})
        own = own or set()

        # Helper: estimates how overcrowded a detour would be if this crowd used it,
        # given where the other crowds are expected to go. Zero means nothing overflows.
        def crowding(p: PathOption) -> float:
            if not loads:
                return 0.0
            total = 0.0
            for rid in p.resources():
                if rid in caps:
                    load = loads.get(rid, 0) - (size if rid in own else 0) + size
                    total += max(0.0, load / caps[rid] - 1.0)
            return total

        # Least crowded detours first, then the shortest; keep just enough to reach k choices.
        pool.sort(key=lambda p: (round(crowding(p), 9), getattr(p, weight)))
        chosen.extend(pool[: k - len(chosen)])
        return chosen

    # --------------------------------------------------------- serialisation
    # Converts the venue into plain lists and labels so it can be sent to the website or saved.
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "locations": [asdict(l) for l in self.locations],
            "routes": [asdict(r) for r in self.routes],
            "crowd_groups": [asdict(g) for g in self.crowd_groups],
        }

    # The reverse of to_dict: rebuilds a venue from plain data, such as a file or a website upload.
    # Missing optional details fall back to sensible defaults.
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
