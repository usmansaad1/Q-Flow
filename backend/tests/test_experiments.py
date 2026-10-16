# WHAT THIS FILE IS FOR: automatic checks for the research experiments, from random venue
# generation through saving results to producing spreadsheets and charts.
# Small settings are used so the whole file runs in a short time.
"""Experiment runner, storage, export and API checks (small settings, fast)."""
import warnings

import pytest

# Hide library warnings during the tests.
warnings.filterwarnings("ignore")

from app.core.charts import export_experiment
from app.core.experiments import ScalingConfig, DepthConfig, VersusConfig, NoiseConfig, run_experiment
from app.core.generator import generate_venue
from app.core.problem import RoutingProblem
from app.core.solvers import solve_naive, solve_exact
from app.core.solvers.quantum import optimise_parameters, solve_qaoa_ideal
from app.core.storage import Storage


# Gives each test its own empty database in a temporary folder.
@pytest.fixture
def store(tmp_path):
    return Storage(tmp_path / "test.db")


# Checks that a random venue with N crowd groups always needs exactly 2 times N qubits.
@pytest.mark.parametrize("groups", [2, 3, 4, 5, 6])
def test_generator_controls_qubit_count(groups):
    p = RoutingProblem(generate_venue(groups, seed=1), paths_per_group=2)
    assert p.num_qubits == 2 * groups


# Checks that the same seed (starting number) always makes the same venue, and that
# at least 7 in 10 random venues are crowded enough that the nearest exit plan is not best.
def test_generator_is_deterministic_and_congested():
    a, b = generate_venue(4, seed=42), generate_venue(4, seed=42)
    assert a.to_dict() == b.to_dict()
    congested = 0
    for seed in range(10):
        p = RoutingProblem(generate_venue(4, seed=seed))
        if solve_naive(p).evaluation["energy"] > solve_exact(p).evaluation["energy"] + 1e-9:
            congested += 1
    assert congested >= 7  # most instances need real optimisation


# Checks that an experiment and its run are saved and read back unchanged, and fully removed on delete.
def test_storage_round_trip(store):
    eid = store.create_experiment("scaling", "t", {"a": 1})
    store.add_run({"experiment_id": eid, "instance": "x", "num_qubits": 4, "method": "m", "solver": "s",
                   "prob_optimal": 0.5, "details": {"k": [1, 2]}})
    store.finish_experiment(eid, {"rows": [{"num_qubits": 4}]})
    e = store.get_experiment(eid)
    assert e["status"] == "done" and e["config"] == {"a": 1} and e["num_runs"] == 1
    assert store.get_runs(eid, include_details=True)[0]["details"] == {"k": [1, 2]}
    store.delete_experiment(eid)
    assert store.get_experiment(eid) is None and store.get_runs(eid) == []


# Checks that each of the four experiments finishes, stores runs and a summary,
# and exports a runs table, a summary table and a chart that are not empty.
@pytest.mark.parametrize("kind,cfg", [
    ("scaling", ScalingConfig(sizes=[4], instances=1, shots=512)),
    ("noise", NoiseConfig(presets=["micro_hall"], levels=[0, 2], fake_backends=[], shots=512)),
    ("depth", DepthConfig(presets=["micro_hall"], reps_list=[1, 2], shots=512)),
    ("versus", VersusConfig(presets=["micro_hall"], fake_backend=None, shots=512)),
])
def test_each_experiment_runs_and_exports(kind, cfg, store, tmp_path):
    eid = run_experiment(kind, cfg, store, log=lambda _: None)
    exp = store.get_experiment(eid)
    assert exp["status"] == "done" and exp["num_runs"] > 0 and exp["summary"]["rows"]
    paths = export_experiment(store, eid, tmp_path / "out")
    assert all(p.exists() and p.stat().st_size > 0 for p in paths.values())
    assert set(paths) == {"runs", "summary", "chart"}


# Checks that an experiment given bad settings (an odd size) is saved as failed, not lost.
def test_failed_experiment_is_recorded(store):
    with pytest.raises(ValueError):
        run_experiment("scaling", ScalingConfig(sizes=[5], instances=1), store, log=lambda _: None)
    assert store.list_experiments()[0]["status"] == "failed"


# Checks that reusing already tuned quantum settings still counts the tuning time in the run time,
# so quantum timings are never flattered.
def test_reused_parameters_still_count_training_time():
    p = RoutingProblem(generate_venue(2, seed=3))
    trained = optimise_parameters(p, 1)
    r = solve_qaoa_ideal(p, reps=1, shots=256, trained=trained)
    assert r.runtime_s >= trained["optimise_time_s"]
    assert r.extra["timing"]["training_s"] == trained["optimise_time_s"]


# Checks that through the web API an experiment can be started, read back with its runs,
# shown as a chart picture and deleted, and that bad settings are refused.
def test_api_experiment_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("QFLOW_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("QFLOW_RESULTS", str(tmp_path / "results"))
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/v1/experiments", json={"kind": "depth", "quick": True,
                                            "config": {"presets": ["micro_hall"], "reps_list": [1], "shots": 512}})
    assert r.status_code == 202
    eid = r.json()["id"]
    exp = c.get(f"/api/v1/experiments/{eid}").json()     # TestClient runs background tasks before returning
    assert exp["status"] == "done" and len(exp["runs"]) == 2
    chart = c.get(f"/api/v1/experiments/{eid}/chart")
    assert chart.status_code == 200 and chart.headers["content-type"] == "image/png"
    assert c.post("/api/v1/experiments", json={"kind": "depth", "config": {"bogus": 1}}).status_code == 422
    assert c.delete(f"/api/v1/experiments/{eid}").status_code == 204
