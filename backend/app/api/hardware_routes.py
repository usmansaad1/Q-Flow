"""
Stage 5 routes. A real IBM run is a background job: submit it, then poll until IBM
finishes. Queues can take minutes or hours, so no web request waits for them.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.schemas import ProblemSettings, QuantumSettings, VenueIn
from app.core.problem import RoutingProblem, Weights
from app.core.solvers import hardware
from app.core.solvers.base import SolverResult
from app.core.solvers.exact import solve_exact
from app.core.solvers.naive import solve_naive
from app.core.storage import Storage
from app.core.venue import Venue

router = APIRouter(prefix="/api/v1/hardware", tags=["IBM hardware"])


class HardwareRequest(BaseModel):
    venue: VenueIn
    settings: ProblemSettings = ProblemSettings()
    quantum: QuantumSettings = QuantumSettings()
    device: Optional[str] = None  # None lets IBM pick the least busy device


def _build(venue: dict, settings: dict) -> RoutingProblem:
    s = ProblemSettings(**settings)
    try:
        return RoutingProblem(Venue.from_dict(venue), Weights(**s.weights.model_dump()),
                              paths_per_group=s.paths_per_group, penalty_factor=s.penalty_factor)
    except ValueError as e:
        raise HTTPException(422, str(e))


def _assemble(problem: RoutingProblem, result: SolverResult) -> dict:
    """The same response shape /api/v1/optimize returns, so the Lab shows it unchanged."""
    baseline = solve_naive(problem)
    exact = solve_exact(problem)
    e_opt, e_worst = exact.extra["optimal_energy"], exact.extra["worst_feasible_energy"]
    span = e_worst - e_opt
    e = result.evaluation["energy"]
    m = result.extra["metrics"]
    quality = {
        "optimal_energy": e_opt,
        "approximation_ratio": 1.0 if span == 0 else max(0.0, (e_worst - e) / span),
        "is_optimal": abs(e - e_opt) < 1e-9,
        "baseline_approx_ratio": 1.0 if span == 0 else max(0.0, (e_worst - baseline.evaluation["energy"]) / span),
        "baseline_is_optimal": abs(baseline.evaluation["energy"] - e_opt) < 1e-9,
        "prob_optimal": m["prob_optimal"],
        "prob_feasible": m["prob_feasible"],
        "mean_approx_ratio": m["mean_approx_ratio"],
        "random_baseline": m["random_baseline"],
    }
    most = m["most_likely"]
    typical = SolverResult.build(problem, result.solver, "typical", most["bitstring"], 0.0)
    return {
        "problem": problem.describe(),
        "result": result.to_dict(problem),
        "baseline": baseline.to_dict(problem),
        "quality": quality,
        "typical": {**typical.to_dict(problem), "probability": most["probability"]},
    }


def _finish(job_id: str, row: dict) -> dict:
    """IBM says the job is done: compute the answer once, save it to Run history, keep it."""
    p = row["payload"]
    problem = _build(p["venue"], p["settings"])
    result = hardware.job_result(problem, job_id, p["meta"], solve_exact(problem))
    response = _assemble(problem, result)
    q = response["quality"]
    response["run_id"] = Storage().save_lab_run(
        problem.venue.name, "ibm_hardware", problem.num_qubits,
        q.get("mean_approx_ratio", q.get("approximation_ratio")),
        {**response, "venue": problem.venue.to_dict(), "settings": p["settings"], "solver": "ibm_hardware"})
    Storage().update_hardware_job(job_id, response=response)
    return response


@router.get("/devices")
def devices():
    try:
        return hardware.list_devices()
    except hardware.HardwareUnavailable as e:
        raise HTTPException(503, str(e))


@router.post("/dry-run")
def dry_run(req: HardwareRequest):
    problem = _build(req.venue.model_dump(), req.settings.model_dump())
    try:
        info = hardware.dry_run(problem, reps=req.quantum.reps, device=req.device, seed=req.quantum.seed)
    except hardware.HardwareUnavailable as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {**info, "qubits": problem.num_qubits}


@router.post("/jobs", status_code=202)
def submit_job(req: HardwareRequest):
    problem = _build(req.venue.model_dump(), req.settings.model_dump())
    try:
        meta = hardware.submit(problem, reps=req.quantum.reps, shots=req.quantum.shots,
                               device=req.device, seed=req.quantum.seed)
    except hardware.HardwareUnavailable as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    Storage().save_hardware_job(meta["job_id"], meta["backend"], {
        "venue": problem.venue.to_dict(), "settings": req.settings.model_dump(),
        "quantum": req.quantum.model_dump(), "meta": meta,
    })
    return {"job_id": meta["job_id"], "backend": meta["backend"], "status": "SUBMITTED"}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    store = Storage()
    row = store.get_hardware_job(job_id)
    if not row:
        raise HTTPException(404, f"No IBM job {job_id} is recorded here.")
    if row["response"]:  # already finished and saved: never ask IBM again
        return {**row["response"], "status": "DONE"}
    if row["error"]:
        return {"status": "ERROR", "error": row["error"], "backend": row["backend"], "job_id": job_id}
    try:
        live = hardware.job_status(job_id)
    except hardware.HardwareUnavailable as e:
        raise HTTPException(503, str(e))
    status = live["status"]
    if status == "DONE":
        try:
            return {**_finish(job_id, row), "status": "DONE"}
        except Exception as e:
            store.update_hardware_job(job_id, error=f"Could not read the IBM result: {e}")
            return {"status": "ERROR", "error": f"Could not read the IBM result: {e}",
                    "backend": row["backend"], "job_id": job_id}
    if status in ("ERROR", "CANCELLED"):
        msg = f"IBM reported the job as {status.lower()}."
        store.update_hardware_job(job_id, error=msg)
        return {"status": status, "error": msg, "backend": row["backend"], "job_id": job_id}
    return {"status": status, "queue_position": live["queue_position"],
            "backend": row["backend"], "job_id": job_id}
