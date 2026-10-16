# WHAT THIS FILE IS FOR: automatic checks for small fixes made before the client demo
# and after a code review: solves that are not saved, cleanup after a restart,
# clear error messages and duplicate route detection.
"""Checks for the pre demo fixes: display only solves, interrupted experiments."""
import pytest
import warnings

# Hide library warnings during the tests.
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient

from app.core.storage import Storage
from app.main import app


# Checks that a solve marked "do not record" is not saved to the Lab history, while a normal solve is.
def test_optimize_with_record_false_is_not_saved():
    c = TestClient(app)
    r = c.post("/api/v1/optimize", json={"preset_id": "micro_hall", "solver": "classical_exact", "record": False})
    assert r.status_code == 200 and "run_id" not in r.json()
    assert c.get("/api/v1/lab-runs").json() == []
    r = c.post("/api/v1/optimize", json={"preset_id": "micro_hall", "solver": "classical_exact"})
    assert "run_id" in r.json()
    assert len(c.get("/api/v1/lab-runs").json()) == 1


# Checks that on startup, experiments stuck as running are marked failed as interrupted,
# while finished ones are left alone.
def test_running_experiments_are_marked_interrupted_on_startup():
    store = Storage()
    stuck = store.create_experiment("scaling", "t", {})
    done = store.create_experiment("depth", "t", {})
    store.finish_experiment(done, {"rows": []})
    with TestClient(app):  # entering runs the startup hook
        pass
    assert store.get_experiment(stuck)["status"] == "failed"
    assert "Interrupted" in store.get_experiment(stuck)["error"]
    assert store.get_experiment(done)["status"] == "done"


# Checks that a crowd with no way to any exit gets a plain message naming it, and the venue cannot be saved.
def test_area_with_no_path_to_an_exit_gets_a_plain_message():
    venue = {"name": "X",
             "locations": [{"id": "A", "location_type": "zone"}, {"id": "B", "location_type": "zone"},
                           {"id": "C", "location_type": "zone"}, {"id": "E", "location_type": "exit", "capacity": 100}],
             "routes": [{"from_node": "A", "to_node": "E", "capacity": 100, "length": 10},
                        {"from_node": "B", "to_node": "C", "capacity": 100, "length": 10}],
             "crowd_groups": [{"group_id": "A crowd", "location": "A", "size": 50},
                              {"group_id": "B crowd", "location": "B", "size": 50}]}
    c = TestClient(app)
    r = c.post("/api/v1/problem", json={"venue": venue})
    assert r.status_code == 422 and "B can't reach any exit" in r.json()["detail"]
    assert c.post("/api/v1/venues", json={"venue": venue}).status_code == 422


# Checks that when only one valid plan exists, the quantum result scores a full 100 percent.
def test_single_valid_plan_scores_100_percent_for_quantum():
    venue = {"name": "One exit",
             "locations": [{"id": "A", "location_type": "zone"}, {"id": "E", "location_type": "exit", "capacity": 10}],
             "routes": [{"from_node": "A", "to_node": "E", "capacity": 10, "length": 10}],
             "crowd_groups": [{"group_id": "A crowd", "location": "A", "size": 50}]}
    q = TestClient(app).post("/api/v1/optimize", json={"venue": venue, "solver": "qaoa_ideal", "record": False}).json()["quality"]
    assert q["prob_optimal"] == 1.0 and q["mean_approx_ratio"] == 1.0


# ---------------------------------------------------------------- code review fixes
# Builds a tiny venue with one zone and one exit, ready for routes to be added.
def _two_places():
    from app.core.venue import Venue
    return Venue("t").add_location("A", "zone").add_location("E", "exit", capacity=100)


# Checks that the same two way route drawn twice, once in each direction, is refused as a duplicate.
def test_two_way_route_drawn_twice_in_opposite_directions_is_rejected():
    v = _two_places()
    v.add_route("A", "E", capacity=100, length=10)
    v.add_route("E", "A", capacity=100, length=10)
    with pytest.raises(ValueError, match="Duplicate routes"):
        v.validate()


# Checks that two one way routes going opposite ways between the same places are accepted.
def test_one_way_routes_in_opposite_directions_are_allowed():
    v = _two_places()
    v.add_route("A", "E", capacity=100, length=10, bidirectional=False)
    v.add_route("E", "A", capacity=100, length=10, bidirectional=False)
    v.validate()  # two separate one way corridors are a valid layout


# Checks that deleting an experiment that does not exist answers "not found" (code 404).
def test_deleting_a_missing_experiment_returns_404():
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).delete("/api/v1/experiments/999999").status_code == 404


# Checks that an empty summary is saved as empty, not lost as missing.
def test_empty_experiment_summary_is_kept():
    from app.core.storage import Storage
    s = Storage()
    exp_id = s.create_experiment("depth", "t", {})
    s.finish_experiment(exp_id, summary={})
    assert s.get_experiment(exp_id)["summary"] == {}


# Checks that a crowd is never routed against a one way corridor, and that a crowd whose
# only way out is a one way corridor pointing the wrong way gets the plain "can't reach" message.
def test_crowds_never_walk_a_one_way_route_backwards():
    from app.core.problem import RoutingProblem
    from app.core.venue import Venue
    v = (Venue("t").add_location("Hall", "hall")
         .add_location("Front", "exit", capacity=500).add_location("Back", "exit", capacity=500))
    v.add_route("Front", "Hall", capacity=500, length=5, bidirectional=False)   # entry only: Front to Hall
    v.add_route("Hall", "Back", capacity=500, length=50)
    v.add_group("g", "Hall", 100)
    p = RoutingProblem(v, paths_per_group=2)
    assert {o.path.exit_id for o in p.options} == {"Back"}   # Front is closer but points the wrong way

    w = Venue("t").add_location("Hall", "hall").add_location("Front", "exit", capacity=500)
    w.add_route("Front", "Hall", capacity=500, length=5, bidirectional=False)
    w.add_group("g", "Hall", 100)
    with pytest.raises(ValueError, match="can't reach any exit"):
        RoutingProblem(w)
