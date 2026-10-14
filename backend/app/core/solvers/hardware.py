"""
IBM Quantum hardware solver (Stage 5).

Credentials come from the backend's environment, never from code or the repository:
    QFLOW_IBM_TOKEN     IBM Cloud API key
    QFLOW_IBM_CRN       the instance CRN (starts with crn:v1:)
    QFLOW_IBM_CHANNEL   optional, defaults to ibm_cloud
They can be set in the terminal, or in a file called backend/.env (see backend/.env.example).
Values already set in the terminal win over the file.

A real run has two phases, so a long queue never holds up a web request:
    submit()      trains the QAOA angles on the ideal simulator, transpiles the same
                  circuit for the chosen device and sends one job to IBM.
    job_result()  once IBM reports the job as done, turns the counts into the same
                  metrics every other solver reports.
dry_run() only transpiles for the device. It sends nothing and uses no quota.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

# backend/.env, if the file exists. override=False keeps any value already set in the terminal.
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

from app.core.problem import RoutingProblem
from app.core.solvers.base import SolverResult
from app.core.solvers.quantum import (
    analyse_distribution, build_qaoa_circuit, circuit_stats, counts_to_probs, optimise_parameters,
)


class HardwareUnavailable(RuntimeError):
    """Not signed in, or IBM cannot be reached. The message is shown to the user as it is."""


def service():
    token, crn = os.environ.get("QFLOW_IBM_TOKEN"), os.environ.get("QFLOW_IBM_CRN")
    if not token or not crn:
        raise HardwareUnavailable(
            "IBM hardware is not connected. Set QFLOW_IBM_TOKEN and QFLOW_IBM_CRN in the "
            "backend environment, then restart the backend.")
    from qiskit_ibm_runtime import QiskitRuntimeService
    try:
        return QiskitRuntimeService(channel=os.environ.get("QFLOW_IBM_CHANNEL", "ibm_cloud"),
                                    token=token, instance=crn)
    except Exception as e:  # wrong key, wrong CRN or no network
        raise HardwareUnavailable(f"Could not sign in to IBM Quantum: {e}") from e


def _pending(backend) -> int | None:
    try:
        return backend.status().pending_jobs
    except Exception:
        return None


def list_devices() -> list[dict[str, Any]]:
    out = [{"name": b.name, "num_qubits": b.num_qubits, "pending_jobs": _pending(b)}
           for b in service().backends(operational=True, simulator=False)]
    return sorted(out, key=lambda d: (d["pending_jobs"] or 0, d["name"]))


def _backend(svc, n_qubits: int, device: str | None):
    if device:
        try:
            b = svc.backend(device)
        except Exception as e:
            raise ValueError(f"There is no device called {device} on this account.") from e
        if b.num_qubits < n_qubits:
            raise ValueError(f"{device} has {b.num_qubits} qubits, but this venue needs {n_qubits}.")
        return b
    try:
        return svc.least_busy(min_num_qubits=n_qubits, operational=True, simulator=False)
    except Exception as e:
        raise HardwareUnavailable(f"No IBM device with {n_qubits} qubits is available right now.") from e


def _transpile(logical, backend, seed: int):
    # Optimisation level 1 matches the noisy simulator runs, so the comparison is like for like.
    pm = generate_preset_pass_manager(optimization_level=1, backend=backend, seed_transpiler=seed)
    return pm.run(logical)


def dry_run(problem: RoutingProblem, reps: int = 2, device: str | None = None, seed: int = 7) -> dict:
    svc = service()
    b = _backend(svc, problem.num_qubits, device)
    logical, _ = build_qaoa_circuit(problem, reps, measure=True)
    isa = _transpile(logical, b, seed)
    return {"backend": b.name, "pending_jobs": _pending(b), "transpiled": circuit_stats(isa)}


def _sampler_run(backend, isa, shots: int):
    """Sends the job to IBM. Kept separate so the tests can swap in a local simulator."""
    from qiskit_ibm_runtime import SamplerV2
    return SamplerV2(mode=backend).run([isa], shots=shots)


def submit(problem: RoutingProblem, reps: int = 2, shots: int = 4096,
           device: str | None = None, seed: int = 7) -> dict:
    svc = service()
    b = _backend(svc, problem.num_qubits, device)
    trained = optimise_parameters(problem, reps)
    logical, params = build_qaoa_circuit(problem, reps, measure=True)
    isa = _transpile(logical, b, seed).assign_parameters(dict(zip(params, trained["theta"])))
    job = _sampler_run(b, isa, shots)
    return {
        "job_id": job.job_id(), "backend": b.name, "reps": reps, "shots": shots, "seed": seed,
        "theta": [float(x) for x in trained["theta"]],
        "transpiled": circuit_stats(isa),
        # Kept so the finished run reports the same timing parts as a simulator run.
        "training_s": float(trained["optimise_time_s"]),
        "submitted_at": time.time(),
    }


def job_status(job_id: str) -> dict:
    job = service().job(job_id)
    s = job.status()
    name = getattr(s, "name", str(s)).upper()
    position = None
    if name in ("QUEUED", "INITIALIZING", "VALIDATING"):
        try:
            position = job.queue_position()
        except Exception:
            position = None
    return {"status": name, "queue_position": position}


def job_result(problem: RoutingProblem, job_id: str, meta: dict, reference: SolverResult) -> SolverResult:
    job = service().job(job_id)
    counts = job.result()[0].data.meas.get_counts()
    shots = meta["shots"]
    metrics = analyse_distribution(problem, counts_to_probs(counts, problem.num_variables), shots, reference)
    best = metrics["best_sampled"]
    status = "optimal" if best["is_optimal"] else (
        "feasible" if problem.is_feasible(best["bitstring"]) else "infeasible")
    try:
        usage = float(job.usage())  # seconds the processor was busy; queue time is not counted
    except Exception:
        usage = 0.0
    training = float(meta.get("training_s", 0.0))  # jobs submitted before this field existed: 0
    queue_s, queue_source = _queue_seconds(job, meta, usage)
    reps, theta = meta["reps"], meta["theta"]
    # Same timing parts as a simulator run: training on this computer, then execution
    # (here IBM processor time). Queue wait is reported apart, since it depends on how
    # busy IBM is, not on the algorithm.
    total = training + usage
    return SolverResult.build(
        problem, "ibm_hardware", status, best["bitstring"], total,
        timing={"training_s": training, "execution_s": usage, "total_s": total,
                "queue_s": queue_s, "queue_source": queue_source},
        metrics=metrics,
        config={"reps": reps, "shots": shots, "seed": meta["seed"], "noise": "ibm_hardware",
                "noise_level": None, "fake_backend": meta["backend"]},
        backend=meta["backend"], job_id=job_id,
        noise_model=f"IBM {meta['backend']} (real device)",
        parameters={"gamma": theta[:reps], "beta": theta[reps:]},
        optimal_energy=reference.extra["optimal_energy"],
        circuit={"qubits": problem.num_variables, "reps": reps, "transpiled": meta["transpiled"]},
    )


def _queue_seconds(job, meta: dict, usage: float) -> tuple[float | None, str]:
    """Seconds the job waited in IBM's queue. IBM's own timestamps when available,
    otherwise an estimate from the time between submission and now."""
    try:
        ts = job.metrics().get("timestamps") or {}
        created, running = ts.get("created"), ts.get("running")
        if created and running:
            wait = (datetime.fromisoformat(str(running).replace("Z", "+00:00"))
                    - datetime.fromisoformat(str(created).replace("Z", "+00:00"))).total_seconds()
            return max(0.0, wait), "ibm"
    except Exception:
        pass
    submitted = meta.get("submitted_at")
    if submitted is None:
        return None, "unknown"
    return max(0.0, time.time() - float(submitted) - usage), "estimate"
