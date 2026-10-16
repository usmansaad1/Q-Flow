# Q-Flow: Benchmarking Quantum Optimisation for Crowd Flow Planning

Q-Flow is an experimental platform that asks a practical question:

> **To what extent can current quantum optimisation techniques provide useful solutions to simplified crowd flow planning problems when compared with classical optimisation methods?**

A venue is modelled as a network of areas, routes and exits. Q-Flow decides which route each crowd group should take so that no route or exit is overloaded, while keeping walking distances short. The same problem is solved with classical optimisation and with the Quantum Approximate Optimisation Algorithm (QAOA) using IBM's Qiskit, on an ideal simulator, a noisy simulator and real IBM quantum hardware.

The aim is not to show quantum winning. Classical methods are expected to stay ahead. The aim is to **measure by how much**, and how that gap changes with problem size, hardware noise and circuit depth.

---

## Project status

| Stage | Scope | Status |
|---|---|---|
| 1 | Venue model, shared optimisation formulation, classical solvers, preset venues, tests | Done |
| 2 | QAOA on ideal and noisy simulators, quantum quality metrics | Done |
| 3 | Automated experiments, SQLite storage, CSV and chart export | Done |
| 4 | Web application: overview, venue lab, experiments dashboard, saved venues | Done |
| 5 | Real IBM hardware runs, methodology, QAOA and limitations page | Done |

---

## Findings so far

These come from the default experiment settings and are reproducible with `python -m scripts.run_experiments`, since every run uses fixed random seeds.

**Quantum vs classical at QAOA depth p = 2.** The table shows the probability that a single quantum sample is the optimal plan. The classical exact solver finds it every time.

| Venue | Qubits | Ideal QAOA | Noisy (1x errors) | IBM Torino model | Random guessing |
|---|---|---|---|---|---|
| Micro Hall | 4 | 26.0% | 22.1% | 22.9% | 6.2% |
| Small Event Hall | 6 | 13.4% | 9.2% | 9.4% | 1.6% |
| Concert Venue | 8 | 6.8% | 4.9% | 4.2% | 0.4% |
| Exhibition Centre | 10 | 3.4% | 1.7% | 1.5% | 0.1% |

1. **QAOA genuinely works, but does not compete with classical methods.** Every quantum mode beats random guessing, by about 5 times at 4 qubits. At 12 qubits the ideal simulator beats it by about 60 times, and the noisy simulator by about 28 times. Its chance of finding the optimum still falls steadily as problems grow, while the classical exact solver is always optimal and runs in well under a millisecond.
2. **Ideal QAOA learns the rules more easily than the goal.** Around 96% to 98% of ideal samples are valid plans, but far fewer are optimal. The penalty that enforces "one route per group" dominates the energy landscape, which is a known QAOA limitation.
3. **Noise mainly destroys validity.** On the 10 qubit venue, valid plans fall from 96% (ideal) to about 45% (IBM Torino noise model).
4. **Real chip layouts add cost.** Routing a circuit onto a real IBM qubit layout more than doubles its two qubit gates (88 become 205 on the Exhibition Centre).
5. **Newer hardware does better overall.** The noise model of IBM's newer Torino processor beat the older Brisbane on most measures, although the two tied on the chance of the best plan for two venues.
6. **Depth helps in theory and hurts in practice.** Without noise, deeper circuits keep improving. With noise, quality peaks at p = 2 and then declines on every venue larger than Micro Hall, because each extra layer adds more errors than accuracy. This is the clearest picture of the boundary between theoretical and practical usefulness.

---

## How it works

```
Venue (areas, routes, exits, crowd sizes)
        │
        ▼
Candidate routes per crowd group (shortest paths to the exits)
        │
        ▼
One shared optimisation problem (QUBO): one binary variable per group and route choice
        │
        ├── Naive baseline: everyone takes the nearest exit
        ├── Classical exact: checks every valid plan
        ├── Classical CP SAT: Google OR Tools solver for larger problems
        ├── QAOA ideal: perfect quantum simulation (Qiskit Aer)
        ├── QAOA noisy: simulated hardware errors or calibrated IBM device models
        └── IBM hardware: real IBM processors through Qiskit IBM Runtime
        │
        ▼
One shared evaluator scores every answer the same way
        │
        ▼
Comparison table, venue map colouring, experiment charts
```

The key design rule: **every solver works on exactly the same problem and every answer is scored by exactly the same function**, so quantum and classical results are always comparable.

---

## Getting started

This section takes you from a fresh computer to a running app. Steps 1 to 6 are done once. Step 7 is what you do every time you work on the project.

### 1. Install the requirements

| Tool | Version | Check with |
|---|---|---|
| Python | 3.12 or newer (tested on 3.13) | `python --version` |
| Node.js | 20.9 or newer (includes npm) | `node --version` |
| Git | any recent version | `git --version` |

An IBM Cloud account is only needed for real quantum hardware runs (step 4). Everything else works without one.

On Windows, tick "Add Python to PATH" when installing Python. NumPy and SciPy in this project need Python 3.12 or newer, so `pip install` fails on older versions.

### 2. Get the code

```bash
git clone <repository url>
cd Q-Flow
```

The project has two parts, each with its own folder and its own terminal:

* `backend`: the Python optimisation engine and API (FastAPI, Qiskit, OR-Tools)
* `frontend`: the web app (Next.js)

### 3. Set up the backend

Open a terminal in the project folder:

```bash
cd backend
python -m venv venv
```

This creates a `venv` folder inside `backend` that holds a private copy of Python and every package the project needs, separate from the rest of your computer. It is listed in `.gitignore`, so it is never committed. Everyone who clones the project creates their own.

* **macOS or Linux:** use `python3 -m venv venv` if `python` is not found.
* **Several Python versions installed:** create the folder with a 3.12 or newer version explicitly, for example `py -3.13 -m venv venv` on Windows or `python3.13 -m venv venv` on macOS or Linux.
* **Starting over:** if the `venv` folder breaks or was made with the wrong Python version, delete the folder and run the command again, then reinstall the packages below.

Activate the virtual environment. This must be done in every new terminal before running backend commands:

| System | Command |
|---|---|
| Windows PowerShell | `venv\Scripts\Activate.ps1` |
| Windows Command Prompt | `venv\Scripts\activate.bat` |
| macOS or Linux | `source venv/bin/activate` |

When it is active, the prompt starts with `(venv)`. On Windows PowerShell, if activation fails with "running scripts is disabled", run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Install the packages and run the tests:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -q tests
```

`requirements.txt` lists every backend package with its exact version, so this one command installs everything: FastAPI, Qiskit and its simulators, OR-Tools, SciPy and the rest. Packages go into the `venv` folder, not your main Python.

The first install downloads Qiskit, Qiskit Aer and OR-Tools, so it can take several minutes. All 83 tests should pass.

### 4. Connect IBM Quantum (optional)

Skip this step if you only need the classical solvers and the simulators. The IBM option in the Lab then shows "not connected" and stays disabled.

1. Sign in at `cloud.ibm.com`. Open **Resource list**, find your Quantum instance under **Compute**, open it and copy its **CRN** (it starts with `crn:v1:`). If there is no instance, create one from the catalog by searching for "Quantum Computing" and choosing the free Open plan.
2. Go to **Manage**, then **Access (IAM)**, then **API keys**, and select **Create**. Copy the key from the box that appears before closing it, because IBM shows it only once. A real key is one block of letters and numbers, about 44 characters long. A 36 character value with dashes in an 8, 4, 4, 4 pattern is the key's ID, not the key.
3. In the `backend` folder, copy the example file to a new file called `.env`:

   ```bash
   copy .env.example .env      # Windows
   cp .env.example .env        # macOS or Linux
   ```

4. Open `backend/.env` and fill in both values, with no quotes and no spaces around `=`:

   ```
   QFLOW_IBM_TOKEN=your API key
   QFLOW_IBM_CRN=your CRN
   ```

5. Check the two values without starting the app. With the virtual environment active, from the `backend` folder:

   ```bash
   python -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); from qiskit_ibm_runtime import QiskitRuntimeService as S; S(channel='ibm_cloud', token=os.environ['QFLOW_IBM_TOKEN'], instance=os.environ['QFLOW_IBM_CRN']); print('OK')"
   ```

   It prints `OK` when IBM accepts them. It never prints the key.

`backend/.env` is listed in `.gitignore`, so git will not commit it. Never paste the key into code, chat or a commit. If it is ever shared by mistake, delete it in IBM Cloud and create a new one.

### 5. Set up the frontend

Open a second terminal in the project folder:

```bash
cd frontend
npm install
```

The frontend expects the backend at `http://127.0.0.1:8000`. To use a different address, create `frontend/.env.local` containing `NEXT_PUBLIC_API_URL=http://your-address:port`.

### 6. Start the app for the first time

**Terminal 1, backend** (from `backend`, virtual environment active):

```bash
uvicorn app.main:app --reload
```

The first start takes up to a minute while Qiskit loads. It is ready when the terminal shows `Application startup complete`. Interactive API documentation is then at `http://127.0.0.1:8000/docs`.

**Terminal 2, frontend** (from `frontend`):

```bash
npm run dev
```

Open `http://localhost:3000`. Both terminals must stay open while you use the app.

To check everything works:

1. The Overview page shows the concert venue map with numbers on the right.
2. In **Venue lab**, load **Micro Hall** and press **Run all**. Classical, QAOA simulator and Noisy QAOA columns appear in the comparison.
3. If you did step 4, choose **IBM quantum hardware** and press **Check circuit**. It reports a device, its gate count and its queue, and sends nothing to IBM.

### 7. Every time you work on the project

```bash
# Terminal 1
cd backend
venv\Scripts\Activate.ps1          # or: source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2
cd frontend
npm run dev
```

`--reload` restarts the backend whenever a backend file changes, which also stops any experiment or hardware job it is waiting on. Leave it out (`uvicorn app.main:app --port 8000`) when running full experiments or real hardware jobs.

To run the faster production build of the frontend instead of `npm run dev`:

```bash
npm run build
npm start
```

### After pulling new code

```bash
cd backend
pip install -r requirements.txt    # virtual environment active
cd ../frontend
npm install
```

Then restart both terminals. Update every file from the same version: mixing old and new files is the usual cause of errors after an update.

### Configuration

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `QFLOW_IBM_TOKEN` | `backend/.env` | none | IBM Cloud API key, needed only for real hardware |
| `QFLOW_IBM_CRN` | `backend/.env` | none | CRN of the IBM Quantum instance |
| `QFLOW_IBM_CHANNEL` | `backend/.env` | `ibm_cloud` | IBM connection channel. Leave unset. |
| `QFLOW_DB` | backend environment | `backend/data/qflow.db` | SQLite database location |
| `QFLOW_RESULTS` | backend environment | `backend/results` | Where experiment CSVs and charts are exported |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` | `http://127.0.0.1:8000` | Backend address used by the web app |

Values set in the terminal take priority over `backend/.env`.

### Troubleshooting

| What you see | Cause and fix |
|---|---|
| "Can't reach the Q-Flow backend" in the app | The backend is not running, or is still starting. Start it in terminal 1 and wait for `Application startup complete`. |
| `No module named ...` (for example `dotenv` or `qiskit`) | The virtual environment is not active, or packages are missing. Activate it, then run `pip install -r requirements.txt`. |
| "running scripts is disabled on this system" | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once in PowerShell. |
| `Address already in use` or port 8000 / 3000 busy | Another copy is already running. Close the other terminal, or start on another port (`--port 8001`, then set `NEXT_PUBLIC_API_URL` to match). |
| `500 Internal Server Error` right after updating files | Some files are from an older version. Update every file from the same version and restart the backend. |
| "IBM hardware is not connected" | `backend/.env` was not found or is incomplete. Check it is inside `backend`, named exactly `.env` (not `.env.txt`), and restart the backend. |
| "Could not sign in to IBM Quantum ... Provided API key could not be found" | The value is not a valid key, most often the key's ID. Create a new key in IBM Cloud and copy the value shown at creation. |
| "Could not sign in to IBM Quantum ... Unable to retrieve instances" | The key and the CRN belong to different accounts, or the key cannot see the instance. Use a key and CRN from the same account. |
| An experiment shows "Interrupted" | The backend restarted while it ran. Delete it and run it again, without `--reload`. |
| A hardware run never finishes | Check the queue on the IBM Quantum dashboard. Keep the Lab page open: the result is saved when the page sees the job finish. |

---

## Using the web application

### Overview (`/`)

Opens on a live plan of the Concert Venue. The **Nearest gate** and **Optimised** buttons switch between everyone heading to their closest gate (780 people sent to a gate that can take 500, so 280 people over capacity) and the optimal routing (nobody over capacity). Routes thicken and change colour with load.

### Venue lab (`/lab`)

The main workspace for building venues and comparing solvers.

**Building a venue**

* Load a preset or saved venue from the dropdown, or press the green **New blank venue** button above the edit panel to start from scratch.
* **Add area** and **Add exit** place new boxes on the canvas.
* Drag the **purple dot** on the right edge of a box onto another box to add a route.
* Click any area, exit or route to edit it in the side panel:
  * areas: name, type (zone, hall, seating, event area, corridor, entrance), number of people, and **Split into groups** (1 to 4). By default everyone in an area leaves together by one route; splitting turns them into near equal groups that can each take a different route.
  * exits: name and capacity
  * routes: capacity, length in metres, and optionally travel time in seconds. Leave travel time empty to estimate it from length at walking pace (1.3 m/s); set it for stairs, ramps or slow routes. Custom times appear on the map label.
  * route direction: **Both ways** (the default), or **One way** in either direction, for an exit only turnstile or a one way staircase. One way routes show arrowheads on the map, and crowds are never routed against them.
* Press **Delete** to remove the selected item.

**Saving venues**

* **Save venue** stores the current venue, including its layout, in the database. It then appears under **Your saved venues** in the venue dropdown.
* The status next to the button shows whether there are unsaved changes. Switching venues with unsaved changes asks for confirmation first.
* The **More** menu can download the venue as a `.qflow.json` file, open a venue file, save a copy as a new venue, undo changes since loading, or delete a saved venue.
* Only venues the optimiser can actually solve can be saved. Problems are explained in plain language.
* Saved venues live in the local database, which is not committed. To keep a venue in the repository, for example a demo scenario, download it as a file and commit the file.

Each area with people becomes one crowd group, or several if split. The counter at the top right shows how many qubits the venue needs: crowd groups multiplied by routes considered per group (2 by default). Splitting makes no difference to cost for the classical solvers but adds qubits for quantum ones, so it is off by default. Errors such as a missing exit or duplicate names are explained in plain language.

**Solving**

Choose a solver (Classical, QAOA simulator, Noisy QAOA, or IBM hardware) and press **Run**, or press **Run all** to fill the full comparison.

* Quantum settings: QAOA depth p, number of shots, and for noisy runs either an adjustable error rate or a real IBM device model (Torino, Fez, Brisbane, Sherbrooke).
* **Optimisation priorities** adjusts the weight of congestion, capacity overflow, walking distance and travel time, and how many routes are considered per group.

**Reading the results**

* The buttons over the map switch between the nearest exit plan and each solver's plan. For quantum solvers a second switch chooses between the **most common answer** (the default: what a single quantum run would usually give) and the **best of all shots**.
* Every run is saved automatically. **Run history**, below the results, lists past runs; **Open** restores the venue, settings, table and map. Route colours show load: green under 60%, amber 60% to 85%, red 85% to 100%, wine over capacity.
* The comparison table shows, for each solver:

| Measure | Meaning |
|---|---|
| Typical answer quality | How close answers are to the best plan, from 0% to 100%. For quantum, the average over all shots. |
| Chance of the best plan | How often a single answer is exactly optimal, with the random guessing figure for reference |
| Valid plans | Share of answers that send every group down exactly one route |
| Objective score | The value being minimised; lower is better |
| Congestion score | The congestion part of the objective |
| People over capacity | The fewest people who would have to be taken out for every route and exit to fit. Each person is counted once, even if their path passes several overloaded routes and exits. |
| Overloaded routes and exits | How many routes and exits are over capacity |
| Busiest route or exit | Highest load as a percentage of capacity |
| Training time | Quantum only: choosing the circuit's angles, always on this computer |
| Execution time | Solving or simulating on this computer; for IBM hardware, the time IBM's processor was busy |
| Total time | Training plus execution, comparable across every solver |
| IBM queue wait | Hardware only: time the job waited for IBM's processor, kept out of the total |
| Qubits and two qubit gates | Size of the quantum circuit |

Changing anything that affects the problem clears old results automatically, so the table never mixes answers from different venues. Moving boxes or selecting items does not count as a change.

### Experiments (`/experiments`)

Runs the four experiments from the proposal in the background and stores every result.

* **Quick run** uses small settings for a fast check. **Full run** produces the data for the report.
* The page updates itself while an experiment runs.
* Each experiment has interactive charts, a **Download runs (CSV)** button, a **Report chart (PNG)** for documents, and a full history.

### Methodology (`/methodology`)

Explains the study for clients and reviewers: the research question, how a venue becomes a QUBO, the score and its weights, the classical solvers, how QAOA works step by step, the three quantum execution modes, how each result is measured, the first real hardware results, and the limitations of the model and of current quantum hardware.

---

## Command line tools

All run from the `backend` folder with the venv active.

```bash
python -m scripts.run_classical                 # before vs after on every preset
python -m scripts.run_quantum                   # classical vs ideal vs noisy QAOA table
python -m scripts.run_quantum --reps 3          # different QAOA depth
python -m scripts.run_quantum --skip-fake       # skip the slower IBM device model runs

python -m scripts.run_experiments --quick       # all four experiments, small settings (under a minute)
python -m scripts.run_experiments               # all four, full settings (about 5 minutes)
python -m scripts.run_experiments noise depth   # selected experiments only
python -m scripts.run_experiments --list        # experiments stored in the database
python -m scripts.run_experiments --export 3    # regenerate CSV and chart for experiment 3
```

---

## The optimisation model

Defined in `backend/app/core/problem.py`.

**Decision variables.** For each crowd group, the backend finds candidate routes to the exits (the shortest path to each reachable exit, keeping the best few). Each variable `x = 1` means "this group takes this route". Qubits equal the total number of group and route choices. **No extra (slack) variables are ever added**, which keeps quantum circuits as small as possible.

**Cost function.** A weighted sum of four terms, each adjustable:

| Term | What it penalises |
|---|---|
| Distance | People multiplied by metres walked |
| Travel time | People multiplied by seconds walked (the route's given travel time, or estimated from length at 1.3 m/s) |
| Congestion | The square of each route's and exit's load relative to its capacity |
| Overflow | People beyond capacity on each route and exit |

A penalty term enforces exactly one route per group.

**Overflow approximation.** True overflow, `max(0, load − capacity)`, cannot be written exactly in the quadratic form quantum optimisation needs. Q-Flow fits the best quadratic approximation for each route and exit by least squares over every possible combination of groups using it. The fit is exact when at most two groups share a route or exit, and approximate beyond that. The exact number of people over capacity is always reported separately, so no result hides an overflow. It is calculated as the fewest people who would have to be removed for every route and exit to fit, using a small linear programme, so the same people are never counted twice along one path while separate overloads at different exits still add up.

**Penalty strength.** The penalty is set from the cost of the nearest exit plan, which guarantees that the lowest energy state of the problem is always the best valid plan. The tests verify this by checking every possible answer.

**Bit order.** Variable `i` corresponds to `problem.options[i]`. Qiskit's little endian convention means statevector index `k` and the integer value of a measured bitstring both encode `x_i = (k >> i) & 1`, which matches the formulation directly, so no reordering is needed. A dedicated test confirms the simulator and the formulation agree.

---

## Solvers

| Solver | API name | Description |
|---|---|---|
| Nearest exit | `naive` | Every group takes its shortest route. The "before" baseline. |
| Classical exact | `classical_exact` | Checks every valid plan. Ground truth for all quantum comparisons. |
| Classical CP SAT | `classical_cpsat` | Google OR Tools constraint solver on the same objective, for problems too large to enumerate |
| QAOA ideal | `qaoa_ideal` | QAOA on a perfect simulator |
| QAOA noisy | `qaoa_noisy` | QAOA with simulated hardware errors |
| IBM hardware | `ibm_hardware` | Real IBM processor, run as a background job through `/api/v1/hardware` |

### How QAOA is run

Defined in `backend/app/core/solvers/quantum.py`.

* **Circuit.** Built directly from the shared problem: two qubit `RZZ` and single qubit `RZ` gates for the cost, `RX` gates for the mixer. Coefficients are normalised so parameter ranges are comparable across venues.
* **Parameter training.** For p = 1, a grid search followed by the COBYLA optimiser on the exact statevector. Deeper circuits start from the previous depth's optimum using the INTERP method (Zhou et al., 2020), which avoids unreliable random restarts.
* **Noise models.**
  * *Adjustable error rate:* depolarising gate errors and measurement errors. 1x is roughly current hardware (0.1% single qubit, 1% two qubit, 2% readout). Qubits are fully connected, isolating the effect of noise level alone.
  * *IBM device models:* calibration data and qubit layout of real IBM processors, including the extra SWAP gates needed to fit the circuit onto the chip.
* **Parameter transfer.** Parameters are trained on the ideal simulator and reused for noisy runs, exactly as they will be for real hardware. Retraining under noise was tested and cost about 10 times the runtime with no measurable gain.

### Why "best sample found" is not the headline

With 4 to 10 qubits there are at most 1,024 possible answers, so a few thousand shots will usually find the optimum by chance, even with heavy noise. Reporting only the best sample would make quantum look perfect. Q-Flow therefore reports the **quality of the whole output distribution** (chance of the optimum, valid plan rate, mean approximation ratio), always next to the random guessing baseline.

---

## Experiments

Defined in `backend/app/core/experiments.py`.

| Experiment | Proposal | What varies | Venues |
|---|---|---|---|
| `scaling` | Experiment 1 | Qubits: 4, 6, 8, 10, 12 | 5 random venues per size |
| `noise` | Experiment 2 | Error rate 0x to 10x, plus IBM Torino and Brisbane models | 4 presets |
| `depth` | Experiment 3 | QAOA depth p = 1 to 5, ideal and noisy | 4 presets |
| `versus` | Experiment 4 | Nearest exit, exact, CP SAT, QAOA ideal, noisy, IBM device model | 4 presets |

* **Random venues** for the scaling experiment come from `generator.py`. They are seeded (fully reproducible), congested by design so that optimisation matters, and use exactly 2 qubits per crowd group.
* **Fair noise comparison.** In the noise experiment, parameters are trained once per venue and reused at every noise level, so only the noise changes.
* **Honest timing.** Quantum run times always include parameter training, even when trained parameters are reused, and real hardware runs report the same training, execution and total times as the simulators, with the IBM queue wait shown separately.

### Where results go

* Every solver execution is one row in the SQLite database `backend/data/qflow.db`, which also holds saved venues. This is local working data and is not committed.
* Each experiment is exported to `backend/results/<id>_<kind>/` as `runs.csv` (every run), `summary.csv` (mean and standard deviation per group) and a PNG chart. These exports are committed as the project's evidence.

---

## API reference

Full interactive documentation: `http://127.0.0.1:8000/docs`

### Venues and solving

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service check |
| GET | `/api/v1/presets` | Preset venues with qubit counts |
| GET | `/api/v1/presets/{id}` | Full definition of one preset |
| POST | `/api/v1/problem` | Formulation summary for a venue: variables, qubits, resources |
| POST | `/api/v1/optimize` | Solve a venue; returns the result, the nearest exit baseline and quality metrics |

Example request:

```json
{
  "preset_id": "small_event_hall",
  "solver": "qaoa_noisy",
  "settings": {
    "weights": { "distance": 1, "time": 0, "congestion": 1, "overflow": 2 },
    "paths_per_group": 2
  },
  "quantum": { "reps": 2, "shots": 4096, "noise": "fake_backend", "fake_backend": "FakeTorino" }
}
```

Instead of `preset_id`, a full `venue` object can be sent with `locations`, `routes` and `crowd_groups`.

### Saved venues

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/venues` | Saved venues with qubit counts and crowd totals |
| GET | `/api/v1/venues/{id}` | Full definition of one saved venue |
| POST | `/api/v1/venues` | Save a new venue: `{"venue": {...}}`. Unsolvable venues are rejected. |
| PUT | `/api/v1/venues/{id}` | Update a saved venue |
| DELETE | `/api/v1/venues/{id}` | Delete a saved venue |

### Experiments

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/experiments` | All stored experiments with status |
| POST | `/api/v1/experiments` | Start one in the background: `{"kind": "depth", "quick": true}` |
| GET | `/api/v1/experiments/{id}` | Status, summary and every run (`?details=true` for full run data) |
| GET | `/api/v1/experiments/{id}/chart` | PNG chart |
| DELETE | `/api/v1/experiments/{id}` | Remove an experiment and its runs |

---

## Project structure

```
q-flow/
├── backend/
│   ├── app/
│   │   ├── core/                  optimisation engine, independent of the web layer
│   │   │   ├── venue.py           venue model and candidate route finding
│   │   │   ├── problem.py         shared formulation and evaluator
│   │   │   ├── presets.py         4, 6, 8 and 10 qubit preset venues
│   │   │   ├── generator.py       seeded random venues for scaling experiments
│   │   │   ├── experiments.py     the four experiments
│   │   │   ├── storage.py         SQLite storage for experiments and saved venues
│   │   │   ├── charts.py          CSV and PNG export
│   │   │   └── solvers/           nearest exit, exact, CP SAT, QAOA
│   │   ├── api/schemas.py         request models
│   │   └── main.py                FastAPI routes
│   ├── scripts/                   command line tools
│   ├── tests/                     83 automated tests
│   ├── results/                   exported experiment evidence
│   └── requirements.txt
├── frontend/
│   ├── app/                       pages: overview, lab, experiments
│   ├── components/                venue canvas, lab panels, experiment charts
│   ├── lib/                       API client, types, venue conversion, formatting
│   └── package.json
└── README.md
```

---

## Testing

```bash
cd backend
python -m pytest -q tests
```

The 83 tests check the guarantees every comparison depends on:

* The lowest energy answer is always the best valid plan, checked against every possible answer.
* Every invalid answer scores worse than the optimum.
* People over capacity counts each person once along a path, and adds up separate overloads.
* Splitting a crowd into groups adds qubits and lets it spread over several routes.
* The exact solver, CP SAT and the Qiskit export all agree.
* The Ising conversion used by QAOA matches the formulation exactly.
* Qiskit's bit order matches the formulation.
* Ideal QAOA beats random guessing, and more noise lowers quality.
* Experiments run, store and export correctly, and failures are recorded.
* The API returns correct results for every solver.
* Saved venues keep their layout and any given travel times, estimated times are never stored as given, and unsolvable venues are refused.

The frontend is checked with TypeScript, ESLint and a production build:

```bash
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

---

## Known limitations

* **Simplified movement.** The model decides which exit route each group takes. It does not simulate people moving step by step or visiting several areas before leaving. Results are a visual representation of the optimisation, not a physical crowd simulation.
* **Each crowd group moves as one unit,** as the proposal's binary formulation requires (a group is either on a route or not). A large crowd can be split into up to 4 groups per area to use several routes, at the cost of extra qubits. Each route works in both directions.
* **Shortest routes only.** Each group considers its few shortest routes to the exits; a longer route drawn on the canvas may not be considered if shorter options exist.
* **Overflow is approximated** in the quantum formulation when three or more groups share a route or exit. Exact overflow is always reported.
* **Simulation limit of 16 qubits.** Larger problems are solved classically only.
* **Quantum run times are simulation times** on a laptop and say nothing about future quantum hardware speed.

---

## Technology

| Area | Tools |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| Modelling and classical optimisation | NetworkX, NumPy, SciPy, Google OR Tools |
| Quantum | Qiskit, Qiskit Optimization, Qiskit Aer, Qiskit IBM Runtime |
| Storage and charts | SQLite, Matplotlib |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Venue editor and charts | React Flow, Recharts |
| Typography | IBM Plex Sans and IBM Plex Sans Condensed, self hosted |

---

## Stage 5: real IBM hardware

### Connecting an IBM account

The backend reads the IBM credentials from `backend/.env`, which git ignores. Copy `backend/.env.example` to `backend/.env` and fill in:

```
QFLOW_IBM_TOKEN=your IBM Cloud API key
QFLOW_IBM_CRN=the CRN of your Quantum instance (starts with crn:v1:)
```

The API key comes from IBM Cloud, under Manage, then Access (IAM), then API keys. Its value is shown only once, when it is created. The CRN is on the Quantum instance's details page, listed under Compute in the Resource list. Values set in the terminal take priority over the file. Never commit the key.

Restart the backend, then open `http://127.0.0.1:8000/api/v1/hardware/devices`. A list of devices means the connection works.

### Running on hardware

In the Lab, choose **IBM quantum hardware**, pick a device (or Automatic for the shortest queue) and press **Check circuit**. This adapts the circuit to the device and reports its two qubit gates and depth without sending anything or using quota. **Run** then trains the QAOA angles on the ideal simulator, sends one job to IBM and checks on it every 3 seconds. Keep the page open until the result appears; it is then saved to Run history like any other run.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/hardware/devices` | Devices available to the account, with queue length |
| `POST /api/v1/hardware/dry-run` | Adapt the circuit to a device and report its size. Sends nothing. |
| `POST /api/v1/hardware/jobs` | Submit a job. Returns its job id. |
| `GET /api/v1/hardware/jobs/{job_id}` | Job status, then the full result once IBM finishes |

### First hardware results

ibm_fez, QAOA depth 2, 4,096 shots, one run per size, recorded 9 October 2026. Typical answer quality:

| Qubits | Venue | Ideal | Noisy (1x) | IBM hardware | Best plan (hardware) | Random guess | Valid plans (hardware) | Two qubit gates (hardware) |
|---|---|---|---|---|---|---|---|---|
| 4 | Micro Hall | 66% | 56% | 62% | 24.9% | 6.3% | 88.9% | 25 |
| 6 | Small Event Hall | 73% | 54% | 57% | 9.4% | 1.6% | 76.2% | 69 |
| 8 | Concert Venue | 63% | 42% | 46% | 4.7% | 0.4% | 72.2% | not recorded |
| 10 | Exhibition Centre | 61% | 32% | 23% | 1.4% | 0.1% | 38.9% | 211 |

Hardware quality falls steadily with size, mainly because two qubit gates grow once the circuit is fitted to the chip. The real device did better than the 1x noise model at 4 qubits and worse at 10. These are single runs, so repeat them before quoting averages. The Methodology page in the app explains the method, how QAOA works and the limitations of the study.

### Still open

* Repeat each hardware size to report averages, and compare QAOA depth 1 with depth 2 on hardware.
* Record the demonstration video.
