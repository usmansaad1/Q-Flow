# WHAT THIS FILE IS FOR: automatic checks for venues the user saves in the Lab,
# for walking times on routes, and for how crowds are split across routes.
# Several tests talk to the web API (the address the website uses) through a test client.
"""Saved venues and travel time handling."""
import warnings

import pytest

# Hide library warnings during the tests.
warnings.filterwarnings("ignore")

from app.core.presets import get_preset
from app.core.problem import RoutingProblem
from app.core.venue import DEFAULT_WALK_SPEED, Route, Venue


# Checks that when no walking time is given, one is estimated from length but not saved as if typed in.
def test_estimated_travel_time_is_not_stored_as_given():
    r = Route("A", "B", capacity=100, length=13)
    assert r.travel_time is None
    assert r.effective_travel_time == pytest.approx(13 / DEFAULT_WALK_SPEED)
    d = get_preset("micro_hall").to_dict()
    assert all(route["travel_time"] is None for route in d["routes"])


# Checks that a walking time typed in by the user is used instead of the estimate.
def test_given_travel_time_is_used():
    v = Venue("t").add_location("A", "zone").add_location("E", "exit")
    v.add_route("A", "E", capacity=100, length=10, travel_time=60)
    v.add_group("g", "A", 50)
    p = RoutingProblem(v, paths_per_group=1)
    assert p.options[0].path.travel_time == 60


# Checks that a walking time of zero (or less) is refused.
def test_non_positive_travel_time_rejected():
    v = Venue("t").add_location("A", "zone").add_location("E", "exit")
    v.add_route("A", "E", capacity=100, length=10, travel_time=0)
    v.add_group("g", "A", 50)
    with pytest.raises(ValueError):
        RoutingProblem(v)


# Gives tests a pretend browser that calls the web API, using a fresh empty database.
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QFLOW_DB", str(tmp_path / "venues.db"))
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


# Checks the full life of a saved venue: save, read back unchanged, rename, solve, delete.
def test_saved_venue_lifecycle(client):
    venue = client.get("/api/v1/presets/small_event_hall").json()
    venue["name"] = "My hall"
    venue["routes"][0]["travel_time"] = 42.0

    r = client.post("/api/v1/venues", json={"venue": venue})
    assert r.status_code == 201
    summary = r.json()
    assert summary["name"] == "My hall" and summary["num_qubits"] == 6 and summary["total_people"] == 450
    vid = summary["id"]

    saved = client.get(f"/api/v1/venues/{vid}").json()
    assert saved["routes"][0]["travel_time"] == 42.0                     # given value kept
    assert saved["routes"][1]["travel_time"] is None                     # estimate not stored
    assert [l["x"] for l in saved["locations"]] == [l["x"] for l in venue["locations"]]  # layout kept

    saved["name"] = "Renamed hall"
    assert client.put(f"/api/v1/venues/{vid}", json={"venue": saved}).json()["name"] == "Renamed hall"
    assert [v["name"] for v in client.get("/api/v1/venues").json()] == ["Renamed hall"]

    # A saved venue can be solved like any other.
    opt = client.post("/api/v1/optimize", json={"venue": saved, "solver": "classical_exact"})
    assert opt.status_code == 200

    assert client.delete(f"/api/v1/venues/{vid}").status_code == 204
    assert client.get(f"/api/v1/venues/{vid}").status_code == 404
    assert client.delete(f"/api/v1/venues/{vid}").status_code == 404


# Checks that a venue with no exits is refused with a clear message and nothing is saved.
def test_unsolvable_venue_is_not_saved(client):
    bad = {"name": "No exits", "locations": [{"id": "A", "location_type": "zone"}],
           "routes": [], "crowd_groups": [{"group_id": "g", "location": "A", "size": 10}]}
    r = client.post("/api/v1/venues", json={"venue": bad})
    assert r.status_code == 422 and "can't be saved" in r.json()["detail"]
    assert client.get("/api/v1/venues").json() == []


# Builds a venue whose 300 people are split into a chosen number of nearly equal groups.
def _entrance_venue(groups):
    """300 people at an entrance whose two roads carry 200 each, like the Lab example."""
    v = Venue("split").add_location("Entrance", "entrance")
    v.add_location("Exit A", "exit", capacity=300).add_location("Exit B", "exit", capacity=300)
    v.add_route("Entrance", "Exit A", capacity=200, length=10).add_route("Entrance", "Exit B", capacity=200, length=15)
    sizes = [300 // groups + (1 if i < 300 % groups else 0) for i in range(groups)]
    for i, s in enumerate(sizes):
        v.add_group(f"Entrance crowd {i + 1}", "Entrance", s)
    return RoutingProblem(v)


# Checks that splitting one crowd into two groups lets the best plan use both exits and avoid overcrowding.
def test_splitting_a_crowd_lets_it_use_several_routes():
    from app.core.solvers import solve_exact
    whole, split = _entrance_venue(1), _entrance_venue(2)
    assert whole.num_qubits == 2 and split.num_qubits == 4          # each extra group adds qubits
    assert solve_exact(whole).evaluation["people_over_capacity"] == 100   # one road must take all 300
    best = solve_exact(split)
    assert best.evaluation["people_over_capacity"] == 0                  # 150 each way
    assert {r["exit"] for r in best.routes(split)} == {"Exit A", "Exit B"}


# Checks that the second route offered to a group is a wide detour, not a short but narrow road.
def test_detour_around_a_crowded_road_is_offered():
    """Like the Lab example: the third route should avoid the crowded direct road."""
    v = Venue("detour").add_location("Start", "entrance").add_location("Hub", "corridor")
    v.add_location("Narrow", "hall").add_location("Wide", "hall").add_location("Exit", "exit", capacity=1000)
    v.add_route("Start", "Hub", capacity=200, length=10).add_route("Hub", "Exit", capacity=1000, length=10)
    v.add_route("Start", "Narrow", capacity=50, length=6).add_route("Narrow", "Hub", capacity=500, length=6)
    v.add_route("Start", "Wide", capacity=500, length=9).add_route("Wide", "Hub", capacity=500, length=9)
    v.add_group("a", "Start", 150).add_group("b", "Start", 150)
    p = RoutingProblem(v, paths_per_group=2)
    second = [o.path.nodes for o in p.options if o.group_id == "a"][1]
    assert second[1] == "Wide"          # not the shorter but too narrow route


# Checks that a quantum run from the Lab is saved with its typical answer, can be listed,
# read back and deleted, and that the bulky history is left out.
def test_lab_runs_are_saved_with_typical_answer(client):
    r = client.post("/api/v1/optimize", json={"preset_id": "micro_hall", "solver": "qaoa_ideal",
                                              "quantum": {"reps": 1, "shots": 512}}).json()
    assert r["typical"]["probability"] > 0 and "history" not in r["result"]["extra"]
    runs = client.get("/api/v1/lab-runs").json()
    assert runs[0]["id"] == r["run_id"] and runs[0]["solver"] == "qaoa_ideal"
    saved = client.get(f"/api/v1/lab-runs/{r['run_id']}").json()
    assert saved["venue"]["name"] == "Micro Hall" and saved["typical"]["bitstring"] == r["typical"]["bitstring"]
    assert client.delete(f"/api/v1/lab-runs/{r['run_id']}").status_code == 204
