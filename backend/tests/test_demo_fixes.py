"""Checks for the pre demo fixes: display only solves, interrupted experiments."""
import warnings

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient

from app.core.storage import Storage
from app.main import app


def test_optimize_with_record_false_is_not_saved():
    c = TestClient(app)
    r = c.post("/api/v1/optimize", json={"preset_id": "micro_hall", "solver": "classical_exact", "record": False})
    assert r.status_code == 200 and "run_id" not in r.json()
    assert c.get("/api/v1/lab-runs").json() == []
    r = c.post("/api/v1/optimize", json={"preset_id": "micro_hall", "solver": "classical_exact"})
    assert "run_id" in r.json()
    assert len(c.get("/api/v1/lab-runs").json()) == 1


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


def test_single_valid_plan_scores_100_percent_for_quantum():
    venue = {"name": "One exit",
             "locations": [{"id": "A", "location_type": "zone"}, {"id": "E", "location_type": "exit", "capacity": 10}],
             "routes": [{"from_node": "A", "to_node": "E", "capacity": 10, "length": 10}],
             "crowd_groups": [{"group_id": "A crowd", "location": "A", "size": 50}]}
    q = TestClient(app).post("/api/v1/optimize", json={"venue": venue, "solver": "qaoa_ideal", "record": False}).json()["quality"]
    assert q["prob_optimal"] == 1.0 and q["mean_approx_ratio"] == 1.0
