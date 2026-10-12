"""Stage 5 checks that run without IBM. A local simulator stands in for the real device."""
import warnings

warnings.filterwarnings("ignore")

import pytest
from fastapi.testclient import TestClient
from qiskit_aer.primitives import SamplerV2 as LocalSampler
from qiskit_ibm_runtime.fake_provider import FakeTorino

from app.core.solvers import hardware
from app.main import app


class LocalJob:
    """Looks like an IBM job, but runs on this computer."""

    def __init__(self, result):
        self._result = result

    def job_id(self):
        return "local-1"

    def status(self):
        return "DONE"

    def queue_position(self):
        return None

    def usage(self):
        return 12.5

    def result(self):
        return self._result


@pytest.fixture
def fake_ibm(monkeypatch):
    device = FakeTorino()
    jobs = {}

    class FakeService:
        def least_busy(self, **_):
            return device

        def backend(self, _name):
            return device

        def backends(self, **_):
            return [device]

        def job(self, job_id):
            return jobs[job_id]

    def run(_backend, isa, shots):
        job = LocalJob(LocalSampler().run([isa], shots=shots).result())
        jobs[job.job_id()] = job
        return job

    monkeypatch.setenv("QFLOW_IBM_TOKEN", "test-token")
    monkeypatch.setenv("QFLOW_IBM_CRN", "crn:v1:test")
    monkeypatch.setattr(hardware, "service", lambda: FakeService())
    monkeypatch.setattr(hardware, "_sampler_run", run)
    return device, jobs


def _micro_hall_body(shots=1024):
    venue = TestClient(app).get("/api/v1/presets/micro_hall").json()
    return {"venue": venue, "settings": {}, "quantum": {"reps": 1, "shots": shots}, "device": None}


def test_without_credentials_the_message_is_plain(monkeypatch):
    monkeypatch.delenv("QFLOW_IBM_TOKEN", raising=False)
    monkeypatch.delenv("QFLOW_IBM_CRN", raising=False)
    r = TestClient(app).get("/api/v1/hardware/devices")
    assert r.status_code == 503
    assert "QFLOW_IBM_TOKEN" in r.json()["detail"]


def test_dry_run_checks_the_circuit_and_sends_nothing(fake_ibm):
    _, jobs = fake_ibm
    r = TestClient(app).post("/api/v1/hardware/dry-run", json=_micro_hall_body())
    assert r.status_code == 200
    assert r.json()["transpiled"]["two_qubit_gates"] > 0
    assert jobs == {}


def test_hardware_job_is_submitted_polled_and_saved_once(fake_ibm):
    device, _ = fake_ibm
    c = TestClient(app)
    sub = c.post("/api/v1/hardware/jobs", json=_micro_hall_body())
    assert sub.status_code == 202
    job_id = sub.json()["job_id"]
    done = c.get(f"/api/v1/hardware/jobs/{job_id}").json()
    assert done["status"] == "DONE"
    assert done["result"]["solver"] == "ibm_hardware"
    assert done["result"]["extra"]["backend"] == device.name
    assert 0.0 <= done["quality"]["mean_approx_ratio"] <= 1.0
    assert "run_id" in done
    again = c.get(f"/api/v1/hardware/jobs/{job_id}").json()
    assert again["run_id"] == done["run_id"]  # answered from the saved copy, not saved twice
