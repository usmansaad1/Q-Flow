# Q-Flow: Benchmarking Quantum Optimisation for Crowd Flow Planning

Q-Flow models simplified crowd routing as a binary optimisation problem and compares
classical optimisation with QAOA across ideal simulation, noisy simulation and real
IBM quantum hardware.

## Status

| Stage | Scope | Status |
|---|---|---|
| 1 | Venue model, shared QUBO formulation, classical solvers, presets, tests | Done |
| 2 | QAOA ideal and noisy (Qiskit Aer), quantum metrics | Done |
| 3 | Experiment runner and result storage | Done |
| 4 | Frontend: overview, venue lab, experiments dashboard | Done |
| 5 | IBM hardware runs, documentation, demo | Next |

## Backend quick start

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt

python -m pytest -q tests        # all tests should pass
python -m scripts.run_classical  # before vs after on every preset
python -m scripts.run_quantum    # classical vs ideal vs noisy QAOA
python -m scripts.run_experiments --quick   # all four experiments, small settings
uvicorn app.main:app --reload    # API at http://127.0.0.1:8000/docs
```

## Frontend quick start

Start the backend first (above), then in a second terminal:

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

The frontend talks to `http://127.0.0.1:8000` by default. To point it elsewhere, create
`frontend/.env.local` containing `NEXT_PUBLIC_API_URL=http://your-host:8000`.

| Page | What it does |
|---|---|
| Overview (`/`) | Live before and after on the Concert Venue, plus the project's aims |
| Venue lab (`/lab`) | Load or build a venue, pick a solver and settings, compare results on the plan and in a table |
| Experiments (`/experiments`) | Launch the four experiments, watch progress, explore charts, download CSV |

Built with Next.js 16, React Flow (venue editor), Recharts (charts) and self hosted IBM Plex fonts.

## Design: one formulation, every solver

`app/core/problem.py` builds a single `RoutingProblem`. Every solver optimises it and
every answer is scored by the same `evaluate()`, so comparisons are like for like.

* **Variables.** `x_a = 1` when option `a` (crowd group g takes candidate path j) is chosen.
  Qubits = groups × paths per group. No slack variables, ever.
* **Cost.** Weighted distance + travel time + congestion `(load/capacity)²` + overflow,
  plus a one path per group penalty. All terms are quadratic.
* **Overflow.** True overflow `max(0, load − capacity)` is not quadratic, so it is fitted
  by least squares per resource. Exact when at most two groups share a resource.
  The exact number of people over capacity is always reported separately.
* **Penalty.** Set from the naive plan's cost so the QUBO ground state is provably the
  best feasible plan (verified by brute force in the tests).
* **Bit order.** Bit `i` of a plan is `problem.options[i]`. Note that Qiskit bitstrings
  are little endian; the quantum layer handles the reversal.

## Quantum layer (`app/core/solvers/quantum.py`)

* **Circuit.** QAOA built directly from the shared QUBO via its Ising form
  (`RZZ` cost terms, `RX` mixer). Coefficients are normalised so gamma ranges are
  comparable across problems.
* **Parameter optimisation.** Grid search plus COBYLA at p = 1 on the exact
  statevector; deeper circuits are warm started by INTERP (Zhou et al. 2020).
* **Noise.** `depolarizing` (tunable `noise_level`, all to all connectivity) or
  `fake_backend` (calibrated noise and real qubit layout of an IBM device, e.g.
  FakeTorino, including routing SWAPs). Parameters are transferred from the ideal
  optimum, as they will be on real hardware.
* **Metrics** (identical for every mode, including hardware later):
  probability of the optimal plan, probability of a valid plan, mean approximation
  ratio (invalid plans score 0), best and most likely sampled plans, circuit depth
  and two qubit gate counts, and a uniform random baseline for each.
* **Why not just "best sample found"?** With 4 to 10 qubits, a few thousand shots
  will usually stumble on the optimum even by chance. Distribution quality is the
  honest measure, so it is the headline.

## Experiments (`app/core/experiments.py`)

| Kind | Proposal | What varies | Instances |
|---|---|---|---|
| `scaling` | Exp 1 | Qubits 4, 6, 8, 10, 12 | 5 random venues per size |
| `noise` | Exp 2 | Depolarising x0 to x10, plus FakeTorino and FakeBrisbane | 4 presets |
| `depth` | Exp 3 | QAOA depth p = 1 to 5, ideal and noisy | 4 presets |
| `versus` | Exp 4 | Naive, exact, CP SAT, QAOA ideal, noisy, device model | 4 presets |

```bash
python -m scripts.run_experiments              # all four, full settings (about 5 minutes)
python -m scripts.run_experiments noise depth  # selected experiments
python -m scripts.run_experiments --quick      # smoke test (under a minute)
python -m scripts.run_experiments --list       # stored experiments
python -m scripts.run_experiments --export 3   # regenerate CSV and chart for #3
```

* Every solver execution is one row in `backend/data/qflow.db` (SQLite).
* Each experiment is exported to `backend/results/<id>_<kind>/` as `runs.csv`,
  `summary.csv` (mean and standard deviation per group) and a chart.
* Scaling uses `app/core/generator.py`: seeded random venues, congested by design,
  with exactly 2 qubits per crowd group.
* In the noise experiment, parameters are trained once per venue and reused at every
  noise level, so only the noise changes between runs.
* Quantum runtimes always include parameter training time, even when reused.

## Layout

```
backend/
  app/
    core/            optimisation engine (no web framework imports)
      venue.py       locations, routes, crowd groups, candidate paths
      problem.py     shared QUBO formulation and evaluator
      presets.py     4, 6, 8 and 10 qubit venues
      solvers/       naive baseline, exact enumeration, OR-Tools CP-SAT, QAOA
      generator.py   seeded synthetic venues for scaling experiments
      experiments.py the four experiments
      storage.py     SQLite storage
      charts.py      CSV and PNG export
    api/schemas.py   request models
    main.py          FastAPI routes
  scripts/           runnable demos
  tests/             formulation guarantees
frontend/
  app/               pages: overview, lab, experiments
  components/        venue canvas, lab panels, experiment charts
  lib/               API client, types, venue conversion, formatting
```

## API (current)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/presets` | Preset list with qubit counts |
| GET | `/api/v1/presets/{id}` | Full venue definition |
| POST | `/api/v1/problem` | Formulation summary for a venue |
| POST | `/api/v1/optimize` | Solve; returns result, naive baseline and quality metrics |

`solver` is one of `naive`, `classical_exact`, `classical_cpsat`, `qaoa_ideal`,
`qaoa_noisy` (`ibm_hardware` returns 501 until Stage 5). Quantum runs accept a
`quantum` object: `reps`, `shots`, `noise`, `noise_level`, `fake_backend`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/experiments` | All stored experiments with status |
| POST | `/api/v1/experiments` | Start one in the background: `{"kind", "quick", "config"}` |
| GET | `/api/v1/experiments/{id}` | Status, summary and runs (`?details=true` for full run data) |
| GET | `/api/v1/experiments/{id}/chart` | PNG chart |
| DELETE | `/api/v1/experiments/{id}` | Remove an experiment and its runs |
