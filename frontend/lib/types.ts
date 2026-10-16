// WHAT THIS FILE IS FOR: a dictionary of the shapes of data the website sends and receives.
// The backend is the server that does the maths; it talks to this site through an API (a set of web addresses).
// Every page uses these descriptions so both sides agree on field names.
// Mirrors the backend API (backend/app/api/schemas.py and solver outputs).

// The kinds of place a venue can contain, from entrances to exits.
export type LocationType = "entrance" | "zone" | "hall" | "corridor" | "seating" | "event" | "exit";

// One place in the venue: its name, kind, exit capacity and position on the drawing.
export interface LocationDTO {
  id: string;
  location_type: LocationType;
  capacity?: number | null;
  x?: number | null;
  y?: number | null;
}

// One walkway between two places: how many people it holds, how long it is, and its travel time.
export interface RouteDTO {
  from_node: string;
  to_node: string;
  capacity: number;
  length: number;
  travel_time?: number | null;
  bidirectional?: boolean;
  id?: string | null;
}

// One crowd group: a number of people who start in the same place and move together.
export interface GroupDTO {
  group_id: string;
  location: string;
  size: number;
}

// A whole venue: its name, places, walkways and crowd groups.
export interface VenueDTO {
  name: string;
  description?: string;
  locations: LocationDTO[];
  routes: RouteDTO[];
  crowd_groups: GroupDTO[];
}

// A short line about a venue the user has saved, used in lists.
// Qubits are the basic units of a quantum computer; this counts how many the venue needs.
export interface SavedVenueSummary {
  id: number;
  name: string;
  updated_at: string;
  num_qubits: number | null;
  total_people: number;
}

// A short description of one of the ready made example venues.
export interface PresetInfo {
  id: string;
  name: string;
  description: string;
  num_qubits: number;
  total_people: number;
}

// How much each goal matters when scoring a plan: short distance, short time, less crowding, no overflow.
export interface Weights {
  distance: number;
  time: number;
  congestion: number;
  overflow: number;
}

// The user's settings for a planning problem: goal weights, route choices per group, and rule breaking penalty.
export interface ProblemSettings {
  weights: Weights;
  paths_per_group: number;
  penalty_factor: number;
}

// Settings for a quantum run: circuit layers, number of repeat measurements (shots), and the noise to simulate.
// HOW TO READ THIS FILE: each "interface" is a description of a piece of data and its fields.
// "number | null" means a number or nothing; a "?" after a field name means it may be missing.
export interface QuantumSettings {
  reps: number;
  shots: number;
  noise: "depolarizing" | "fake_backend";
  noise_level: number;
  fake_backend: string;
  seed: number;
}

// The scorecard for one plan: total score, penalties, whether it obeys every rule, and how full each route is.
export interface Evaluation {
  // The total score (lower is better), the score without the penalty, the penalty, and whether the plan obeys the rules.
  energy: number;
  objective: number;
  penalty: number;
  feasible: boolean;
  components: { distance: number; time: number; congestion: number; overflow: number };
  // People on each route and exit, and how full each is (1 means exactly full).
  resource_loads: Record<string, number>;
  utilisation: Record<string, number>;
  capacity_violations: number;
  people_over_capacity: number; // fewest people to remove so every route and exit fits
  total_excess: number;         // excess summed over every route and exit
  max_utilisation: number;
  total_person_distance: number;
}

// The path and exit chosen for one crowd group, and whether that choice is valid.
export interface GroupPlan {
  group_id: string;
  size: number;
  path: string[] | null;
  exit: string | null;
  valid: boolean;
}

// How often a quantum run hit the best or a valid answer, compared with pure random guessing.
export interface QuantumMetrics {
  shots: number;
  prob_optimal: number;
  prob_feasible: number;
  mean_approx_ratio: number;
  random_baseline: { prob_optimal: number; prob_feasible: number; mean_approx_ratio: number };
}

// The answer from one solver (a method that searches for the best plan), with its score and run time.
// The "extra" part holds quantum details such as circuit size, noise and timing.
export interface SolverResultDTO {
  // Which solver, its outcome, the plan as 0s and 1s, and how long it took.
  solver: string;
  status: string;
  bitstring: number[];
  runtime_s: number;
  objective_value: number;
  energy: number;
  evaluation: Evaluation;
  routes: GroupPlan[];
  extra: {
    metrics?: QuantumMetrics;
    noise_model?: string;
    circuit?: { qubits: number; reps: number; transpiled: { depth: number; two_qubit_gates: number } };
    /** Quantum runs. Hardware adds the IBM queue wait, kept apart from the total. */
    timing?: { training_s: number; execution_s: number; total_s: number;
               queue_s?: number | null; queue_source?: "ibm" | "estimate" | "unknown" };
    [k: string]: unknown;
  };
}

// A size summary of the maths problem built from a venue: groups, choices, qubits and limited resources.
export interface ProblemSummary {
  venue: string;
  num_groups: number;
  num_variables: number;
  num_qubits: number;
  num_quadratic_terms: number;
  resources: { id: string; kind: "route" | "exit"; capacity: number }[];
}

// How close a result came to the best possible plan, plus the same figures for random guessing.
export interface Quality {
  // The best possible score, this answer's grade from 0 to 1, and whether it is the best plan.
  optimal_energy: number;
  approximation_ratio: number;
  is_optimal: boolean;
  prob_optimal?: number;
  prob_feasible?: number;
  mean_approx_ratio?: number;
  random_baseline?: QuantumMetrics["random_baseline"];
  baseline_approx_ratio?: number;
  baseline_is_optimal?: boolean;
}

// Everything the server sends back after solving: the problem size, the result, a classical comparison and quality.
export interface OptimizeResponse {
  problem: ProblemSummary;
  result: SolverResultDTO;
  baseline: SolverResultDTO;
  quality: Quality | null;
  /** Quantum only: the most common answer across all shots. */
  typical?: (SolverResultDTO & { probability: number }) | null;
  run_id?: number;
}

// The four kinds of experiment: problem size, noise level, circuit depth, and quantum versus classical.
export type ExperimentKind = "scaling" | "noise" | "depth" | "versus";

// The basic facts about one experiment: its kind, title, progress, settings and summary table.
export interface ExperimentInfo {
  id: number;
  kind: ExperimentKind;
  title: string;
  status: "running" | "done" | "failed";
  config: Record<string, unknown>;
  summary: { rows: Record<string, unknown>[] } | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  num_runs: number;
}

// One row of experiment results: a single solver run with its settings and scores.
export interface RunRow {
  id: number;
  instance: string;
  num_qubits: number;
  method: string;
  solver: string;
  noise_model: string | null;
  noise_level: number | null;
  reps: number | null;
  shots: number | null;
  // The quality measures: chance of the best plan, chance of a valid plan, average grade, and so on.
  prob_optimal: number | null;
  prob_feasible: number | null;
  mean_approx_ratio: number | null;
  best_is_optimal: number | null;
  random_prob_optimal: number | null;
  random_mean_ratio: number | null;
  energy: number | null;
  optimal_energy: number | null;
  two_qubit_gates: number | null;
  depth: number | null;
  runtime_s: number | null;
}

// An experiment together with every run row it produced.
export interface ExperimentDetail extends ExperimentInfo {
  runs: RunRow[];
}

// A short line about one past run from the lab, shown in the run history list.
export interface LabRunSummary {
  id: number;
  venue_name: string;
  solver: string;
  num_qubits: number;
  quality: number | null;
  created_at: string;
}

// A full past run: its results plus the venue and settings used, so it can be reopened.
export interface LabRunDetail extends OptimizeResponse {
  id: number;
  venue: VenueDTO;
  settings: ProblemSettings;
  solver: string;
}

// ------------------------------------------------------------ IBM hardware (Stage 5)
// One real IBM quantum computer: its name, qubit count and how many jobs are waiting.
export interface HardwareDevice {
  name: string;
  num_qubits: number;
  pending_jobs: number | null;
}

// The result of a trial check before sending a job to IBM: the device, queue and circuit size.
export interface HardwareCheck {
  backend: string;
  pending_jobs: number | null;
  qubits: number;
  transpiled: { depth: number; two_qubit_gates: number; [k: string]: unknown };
}

// The progress of a job sent to a real IBM quantum computer, checked again and again until it finishes.
/** A job while IBM works on it. Once DONE, the response carries the full OptimizeResponse fields. */
export type HardwareJobState = {
  job_id: string;
  status: string; // SUBMITTED, QUEUED, RUNNING, DONE, ERROR, CANCELLED ...
  backend?: string;
  queue_position?: number | null;
  error?: string | null;
} & Partial<OptimizeResponse>;
