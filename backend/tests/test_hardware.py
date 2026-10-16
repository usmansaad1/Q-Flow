# WHAT THIS FILE IS FOR: automatic checks for sending jobs to a real IBM quantum computer.
# No IBM account is needed: a stand in pretends to be IBM and runs everything on this computer.
"""Stage 5 checks that run without IBM. A local simulator stands in for the real device."""
import warnings

# Hide library warnings during the tests.
warnings.filterwarnings("ignore")

import pytest
from fastapi.testclient import TestClient
from qiskit_aer.primitives import SamplerV2 as LocalSampler
from qiskit_ibm_runtime.fake_provider import FakeTorino

from app.core.solvers import hardware
from app.main import app


# A pretend IBM job that is already finished and holds a result computed locally.
class LocalJob:
    """Looks like an IBM job, but runs on this computer."""

    # Keeps the finished result to hand back later.
    def __init__(self, result):
        self._result = result

    # Always uses the same made up job number.
    def job_id(self):
        return "local-1"

    # Always reports the job as finished.
    def status(self):
        return "DONE"

    # There is no waiting queue, so no position is given.
    def queue_position(self):
        return None

    # Pretends the quantum processor was busy for 12.5 seconds.
    def usage(self):
        return 12.5

    # Hands back the stored result.
    def result(self):
        return self._result


# Swaps the real IBM connection for a stand in for the length of one test.
# It offers one simulated IBM machine (FakeTorino), runs jobs locally and remembers them.
@pytest.fixture
def fake_ibm(monkeypatch):
    device = FakeTorino()
    jobs = {}

    # A pretend IBM account that always offers the same simulated machine.
    class FakeService:
        # Asked for the least busy machine: gives the simulated one.
        def least_busy(self, **_):
            return device

        # Asked for a machine by name: gives the simulated one whatever the name.
        def backend(self, _name):
            return device

        # Asked for the list of machines: gives just the simulated one.
        def backends(self, **_):
            return [device]

        # Looks up a job sent earlier in this test.
        def job(self, job_id):
            return jobs[job_id]

    # Runs the prepared circuit on a local simulator instead of sending it to IBM.
    def run(_backend, isa, shots):
        job = LocalJob(LocalSampler().run([isa], shots=shots).result())
        jobs[job.job_id()] = job
        return job

    # Fill in pretend IBM login details and plug in the stand ins.
    monkeypatch.setenv("QFLOW_IBM_TOKEN", "test-token")
    monkeypatch.setenv("QFLOW_IBM_CRN", "crn:v1:test")
    monkeypatch.setattr(hardware, "service", lambda: FakeService())
    monkeypatch.setattr(hardware, "_sampler_run", run)
    return device, jobs


# Builds the request for a small quantum job on the smallest preset venue.
def _micro_hall_body(shots=1024):
    venue = TestClient(app).get("/api/v1/presets/micro_hall").json()
    return {"venue": venue, "settings": {}, "quantum": {"reps": 1, "shots": shots}, "device": None}


# Checks that without IBM login details the user gets a clear message naming the missing setting.
def test_without_credentials_the_message_is_plain(monkeypatch):
    monkeypatch.delenv("QFLOW_IBM_TOKEN", raising=False)
    monkeypatch.delenv("QFLOW_IBM_CRN", raising=False)
    r = TestClient(app).get("/api/v1/hardware/devices")
    assert r.status_code == 503
    assert "QFLOW_IBM_TOKEN" in r.json()["detail"]


# Checks that a practice run prepares the circuit for the machine but sends no job at all.
def test_dry_run_checks_the_circuit_and_sends_nothing(fake_ibm):
    _, jobs = fake_ibm
    r = TestClient(app).post("/api/v1/hardware/dry-run", json=_micro_hall_body())
    assert r.status_code == 200
    assert r.json()["transpiled"]["two_qubit_gates"] > 0
    assert jobs == {}


# Checks that a hardware job can be sent and collected, reports its timings correctly,
# and is saved only once even when checked twice.
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
    # Same timing parts as a simulator run; the queue wait is reported apart from the total.
    t = done["result"]["extra"]["timing"]
    assert t["execution_s"] == 12.5                     # LocalJob.usage(): processor seconds
    assert t["training_s"] > 0
    assert t["total_s"] == pytest.approx(t["training_s"] + t["execution_s"])
    assert done["result"]["runtime_s"] == pytest.approx(t["total_s"])
    assert t["queue_s"] is not None and t["queue_source"] == "estimate"  # LocalJob has no IBM timestamps
    again = c.get(f"/api/v1/hardware/jobs/{job_id}").json()
    assert again["run_id"] == done["run_id"]  # answered from the saved copy, not saved twice
