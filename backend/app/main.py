# WHAT THIS FILE IS FOR: the front door of the Q-Flow backend server.
# The web app talks to it through an API (a set of web addresses that answer with data).
# It lists every address: venues, presets, single optimisation runs, run history and experiments.
# The real maths lives in app.core; this file only passes requests to it and returns answers.
"""Q-Flow API. The optimisation engine lives in app.core and never imports FastAPI."""
from contextlib import asynccontextmanager
from dataclasses import asdict as dc_asdict

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.hardware_routes import router as hardware_router
from app.api.schemas import ExperimentRequest, OptimizeRequest, ProblemRequest, VenueSaveRequest
from app.core.charts import export_experiment
from app.core.experiments import CONFIGS, TITLES, quick_config, run_experiment
from app.core.storage import Storage, results_dir
from app.core.presets import PRESETS, get_preset
from app.core.problem import RoutingProblem, Weights
from app.core.solvers.base import SolverResult
from app.core.solvers import CLASSICAL_SOLVERS, QUANTUM_SOLVERS, solve_exact, solve_naive
from app.core.venue import Venue

# Runs once when the server starts up, before it answers any request.
# It tidies up experiments that were cut off when the server last stopped.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # An experiment left "running" by a previous backend process would otherwise stay
    # running forever in the app, with its Delete button disabled.
    Storage().mark_interrupted()
    yield


# Creates the server itself and sets its name and version number.
# The CORS setting lets the web app running on port 3000 of this computer talk to it.
# It also plugs in the extra IBM hardware addresses from hardware_routes.py.
app = FastAPI(title="Q-Flow Optimisation Engine", version="0.5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(hardware_router)



# Turns a request into a routing problem the solvers can work on.
# The venue comes either from a ready made preset or from a venue the user drew.
# Sends back a clear error if the venue is missing or cannot be solved.
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


# A simple "are you alive?" check that always answers healthy while the server runs.
@app.get("/health")
def health():
    return {"status": "healthy", "service": "q-flow-backend"}


# Lists the built in example venues, with how many people and qubits each one needs.
# A qubit is one unit of a quantum computer; bigger venues need more of them.
@app.get("/api/v1/presets")
def list_presets():
    out = []
    for pid, factory in PRESETS.items():
        v = factory()
        out.append({"id": pid, "name": v.name, "description": v.description,
                    "num_qubits": RoutingProblem(v).num_qubits, "total_people": v.total_people})
    return out


# Sends back the full layout of one example venue, or "not found" if the name is wrong.
@app.get("/api/v1/presets/{preset_id}")
def get_preset_venue(preset_id: str):
    try:
        return get_preset(preset_id).to_dict()
    except KeyError as e:
        raise HTTPException(404, str(e))


# Opens the database where venues, runs and experiments are kept.
def get_store() -> Storage:
    return Storage()  # reads QFLOW_DB each time, so tests can point it elsewhere


# ============================================================ saved venues
# Checks a venue before saving it, and refuses one the optimiser could not solve.
def _checked_venue(req: VenueSaveRequest) -> dict:
    """Only venues the optimiser can actually solve are saved."""
    venue = Venue.from_dict(req.venue.model_dump())
    try:
        RoutingProblem(venue)
    except ValueError as e:
        raise HTTPException(422, f"This venue can't be saved yet: {e}")
    return venue.to_dict()


# Makes a short summary card for a saved venue: name, last change, qubits and total people.
# If the venue cannot be solved any more, the qubit count is left empty.
def _venue_summary(v: dict) -> dict:
    try:
        qubits = RoutingProblem(Venue.from_dict(v)).num_qubits
    except ValueError:
        qubits = None
    return {"id": v["id"], "name": v["name"], "updated_at": v["updated_at"], "num_qubits": qubits,
            "total_people": sum(g["size"] for g in v.get("crowd_groups", []))}


# Lists every venue the user has saved, as short summaries.
@app.get("/api/v1/venues")
def list_saved_venues():
    return [_venue_summary(v) for v in get_store().list_venues()]


# Sends back the full details of one saved venue.
@app.get("/api/v1/venues/{venue_id}")
def get_saved_venue(venue_id: int):
    v = get_store().get_venue(venue_id)
    if not v:
        raise HTTPException(404, f"Saved venue {venue_id} not found.")
    return v


# Saves a new venue after checking it, then returns its summary.
@app.post("/api/v1/venues", status_code=201)
def save_venue(req: VenueSaveRequest):
    data = _checked_venue(req)
    return _venue_summary(get_store().get_venue(get_store().save_venue(data)))


# Replaces a saved venue with an edited version, after checking it.
@app.put("/api/v1/venues/{venue_id}")
def update_saved_venue(venue_id: int, req: VenueSaveRequest):
    data = _checked_venue(req)
    if not get_store().update_venue(venue_id, data):
        raise HTTPException(404, f"Saved venue {venue_id} not found.")
    return _venue_summary(get_store().get_venue(venue_id))


# Deletes a saved venue for good.
@app.delete("/api/v1/venues/{venue_id}", status_code=204)
def delete_saved_venue(venue_id: int):
    if not get_store().delete_venue(venue_id):
        raise HTTPException(404, f"Saved venue {venue_id} not found.")


# Describes the maths problem for a venue without solving it.
# The app uses this to show how big the problem is before a run.
@app.post("/api/v1/problem")
def describe_problem(req: ProblemRequest):
    """Formulation summary: decision variables, qubits, resources, penalty."""
    return build_problem(req).describe()


# Solves one venue with the chosen method and reports how good the answer is.
# Methods are classical (normal computer) or QAOA, a quantum method run on a simulator.
# It also compares against a simple "everyone takes the nearest exit" plan.
@app.post("/api/v1/optimize")
def optimize(req: OptimizeRequest):
    # Step 1: build the problem and run the chosen solver.
    problem = build_problem(req)
    if req.solver == "ibm_hardware":
        raise HTTPException(400, "IBM hardware runs are background jobs. Use /api/v1/hardware/jobs instead.")
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

    # Step 2: score the answer against the simple plan and the perfect answer.
    # A score of 1.0 means as good as the perfect answer; 0 means as bad as the worst.
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

    # Step 3: put the reply together for the app.
    response = {
        "problem": problem.describe(),
        "result": result.to_dict(problem),
        "baseline": baseline.to_dict(problem),
        "quality": quality,
        "typical": None,
    }
    if "metrics" in result.extra:
        # The most common quantum answer: what a single run would usually give. The
        # "result" is the best of all shots, which flatters quantum on small problems.
        ml = result.extra["metrics"]["most_likely"]
        typical = SolverResult.build(problem, result.solver, "typical", ml["bitstring"], 0.0)
        response["typical"] = {**typical.to_dict(problem), "probability": ml["probability"]}
    response["result"]["extra"].pop("history", None)  # large and unused by the app

    # Step 4: save the run to Run history, unless the caller asked not to.
    # Every Lab run is recorded (proposal Section 12: "solver results").
    if not req.record:
        return response
    q = quality or {}
    run_quality = q.get("mean_approx_ratio", q.get("approximation_ratio"))
    response["run_id"] = get_store().save_lab_run(
        problem.venue.name, req.solver, problem.num_qubits, run_quality,
        {**response, "venue": problem.venue.to_dict(), "settings": req.settings.model_dump(), "solver": req.solver})
    return response


# Lists every past Lab run from Run history.
@app.get("/api/v1/lab-runs")
def list_lab_runs():
    return get_store().list_lab_runs()


# Sends back the full saved details of one past run, so the app can show it again.
@app.get("/api/v1/lab-runs/{run_id}")
def get_lab_run(run_id: int):
    r = get_store().get_lab_run(run_id)
    if not r:
        raise HTTPException(404, f"Run {run_id} not found.")
    return r


# Deletes one past run from Run history.
@app.delete("/api/v1/lab-runs/{run_id}", status_code=204)
def delete_lab_run(run_id: int):
    if not get_store().delete_lab_run(run_id):
        raise HTTPException(404, f"Run {run_id} not found.")


# =============================================================== experiments
# Runs a whole experiment quietly in the background.
# Any failure is already written to the experiment's record, so it is not raised again here.
def _execute(kind: str, config, exp_id: int) -> None:
    try:
        run_experiment(kind, config, get_store(), log=lambda _: None, exp_id=exp_id)
    except Exception:
        pass  # failure details are already stored on the experiment row


# Lists every experiment, whether finished, running or failed.
@app.get("/api/v1/experiments")
def list_experiments():
    return get_store().list_experiments()


# Starts a new experiment, such as a scaling or noise study, and replies straight away.
# "Quick" mode uses smaller settings; the request can also override single settings.
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


# Sends back one experiment and its individual runs.
# Setting "details" to true also includes the full data of each run.
@app.get("/api/v1/experiments/{exp_id}")
def get_experiment(exp_id: int, details: bool = False):
    store = get_store()
    exp = store.get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, f"Experiment {exp_id} not found.")
    return {**exp, "runs": store.get_runs(exp_id, include_details=details)}


# Draws the chart for a finished experiment and sends it as a picture.
# It refuses if the experiment is still running or has failed.
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


# Deletes an experiment and its runs.
@app.delete("/api/v1/experiments/{exp_id}", status_code=204)
def delete_experiment(exp_id: int):
    if not get_store().delete_experiment(exp_id):
        raise HTTPException(404, f"Experiment {exp_id} not found.")
