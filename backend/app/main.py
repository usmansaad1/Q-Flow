"""Q-Flow API. The optimisation engine lives in app.core and never imports FastAPI."""
from dataclasses import asdict

from dataclasses import asdict as dc_asdict

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.schemas import ExperimentRequest, OptimizeRequest, ProblemRequest
from app.core.charts import export_experiment
from app.core.experiments import CONFIGS, TITLES, quick_config, run_experiment
from app.core.storage import Storage, results_dir
from app.core.presets import PRESETS, get_preset
from app.core.problem import RoutingProblem, Weights
from app.core.solvers import CLASSICAL_SOLVERS, QUANTUM_SOLVERS, solve_exact, solve_naive
from app.core.venue import Venue

app = FastAPI(title="Q-Flow Optimisation Engine", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)



def build_problem(req: ProblemRequest) -> RoutingProblem:
    if req.preset_id:
        try:
            venue = get_preset(req.preset_id)
        except KeyError as e:
            raise HTTPException(404, str(e))
    elif req.venue:
        venue = Venue.from_dict(req.venue.model_dump())
    else:
        raise HTTPException(400, "Provide either preset_id or venue.")
    s = req.settings
    try:
        return RoutingProblem(venue, Weights(**s.weights.model_dump()),
                              paths_per_group=s.paths_per_group, penalty_factor=s.penalty_factor)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/health")
def health():
    return {"status": "healthy", "service": "q-flow-backend"}


@app.get("/api/v1/presets")
def list_presets():
    out = []
    for pid, factory in PRESETS.items():
        v = factory()
        out.append({"id": pid, "name": v.name, "description": v.description,
                    "num_qubits": RoutingProblem(v).num_qubits, "total_people": v.total_people})
    return out


@app.get("/api/v1/presets/{preset_id}")
def get_preset_venue(preset_id: str):
    try:
        return get_preset(preset_id).to_dict()
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/v1/problem")
def describe_problem(req: ProblemRequest):
    """Formulation summary: decision variables, qubits, resources, penalty."""
    return build_problem(req).describe()


@app.post("/api/v1/optimize")
def optimize(req: OptimizeRequest):
    problem = build_problem(req)
    if req.solver == "ibm_hardware":
        raise HTTPException(501, "IBM hardware execution arrives in Stage 5.")
    q = req.quantum
    try:
        if req.solver == "qaoa_ideal":
            result = QUANTUM_SOLVERS["qaoa_ideal"](problem, reps=q.reps, shots=q.shots, seed=q.seed)
        elif req.solver == "qaoa_noisy":
            result = QUANTUM_SOLVERS["qaoa_noisy"](
                problem, noise=q.noise, reps=q.reps, shots=q.shots, seed=q.seed,
                noise_level=q.noise_level, fake_backend=q.fake_backend,
                optimise_under_noise=q.optimise_under_noise)
        else:
            result = CLASSICAL_SOLVERS[req.solver](problem)
    except ValueError as e:
        raise HTTPException(422, str(e))

    # Before vs after, plus quality relative to the exact optimum where it is computable.
    baseline = solve_naive(problem)
    quality = None
    try:
        exact = solve_exact(problem)
        e_opt, e_worst = exact.extra["optimal_energy"], exact.extra["worst_feasible_energy"]
        e = result.evaluation["energy"]
        span = e_worst - e_opt
        quality = {
            "optimal_energy": e_opt,
            "approximation_ratio": 1.0 if span == 0 else max(0.0, (e_worst - e) / span),
            "is_optimal": abs(e - e_opt) < 1e-9,
            # The nearest exit plan scored on the same scale, for before vs after.
            "baseline_approx_ratio": 1.0 if span == 0 else max(0.0, (e_worst - baseline.evaluation["energy"]) / span),
            "baseline_is_optimal": abs(baseline.evaluation["energy"] - e_opt) < 1e-9,
        }
        if "metrics" in result.extra:  # quantum: report distribution quality, not just best sample
            m = result.extra["metrics"]
            quality.update({k: m[k] for k in ("prob_optimal", "prob_feasible", "mean_approx_ratio")})
            quality["random_baseline"] = m["random_baseline"]
    except ValueError:
        pass  # too large for exhaustive search

    return {
        "problem": problem.describe(),
        "result": result.to_dict(problem),
        "baseline": baseline.to_dict(problem),
        "quality": quality,
    }


# =============================================================== experiments
def get_store() -> Storage:
    return Storage()  # reads QFLOW_DB each time, so tests can point it elsewhere


def _execute(kind: str, config, exp_id: int) -> None:
    try:
        run_experiment(kind, config, get_store(), log=lambda _: None, exp_id=exp_id)
    except Exception:
        pass  # failure details are already stored on the experiment row


@app.get("/api/v1/experiments")
def list_experiments():
    return get_store().list_experiments()


@app.post("/api/v1/experiments", status_code=202)
def start_experiment(req: ExperimentRequest, background: BackgroundTasks):
    """Starts an experiment in the background. Poll GET /api/v1/experiments/{id} for status."""
    base = dc_asdict(quick_config(req.kind)) if req.quick else {}
    try:
        config = CONFIGS[req.kind](**{**base, **req.config})
    except TypeError as e:
        raise HTTPException(422, f"Invalid config for '{req.kind}': {e}")
    exp_id = get_store().create_experiment(req.kind, TITLES[req.kind], dc_asdict(config))
    background.add_task(_execute, req.kind, config, exp_id)
    return {"id": exp_id, "status": "running"}


@app.get("/api/v1/experiments/{exp_id}")
def get_experiment(exp_id: int, details: bool = False):
    store = get_store()
    exp = store.get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, f"Experiment {exp_id} not found.")
    return {**exp, "runs": store.get_runs(exp_id, include_details=details)}


@app.get("/api/v1/experiments/{exp_id}/chart")
def experiment_chart(exp_id: int):
    store = get_store()
    exp = store.get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, f"Experiment {exp_id} not found.")
    if exp["status"] != "done":
        raise HTTPException(409, f"Experiment is {exp['status']}.")
    paths = export_experiment(store, exp_id, results_dir() / f"{exp_id:03d}_{exp['kind']}")
    return FileResponse(paths["chart"], media_type="image/png")


@app.delete("/api/v1/experiments/{exp_id}", status_code=204)
def delete_experiment(exp_id: int):
    get_store().delete_experiment(exp_id)
