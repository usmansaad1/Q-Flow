// Mirrors the backend API (backend/app/api/schemas.py and solver outputs).

export type LocationType = "entrance" | "zone" | "hall" | "corridor" | "seating" | "event" | "exit";

export interface LocationDTO {
  id: string;
  location_type: LocationType;
  capacity?: number | null;
  x?: number | null;
  y?: number | null;
}

export interface RouteDTO {
  from_node: string;
  to_node: string;
  capacity: number;
  length: number;
  travel_time?: number | null;
  bidirectional?: boolean;
  id?: string | null;
}

export interface GroupDTO {
  group_id: string;
  location: string;
  size: number;
}

export interface VenueDTO {
  name: string;
  description?: string;
  locations: LocationDTO[];
  routes: RouteDTO[];
  crowd_groups: GroupDTO[];
}

export interface SavedVenueSummary {
  id: number;
  name: string;
  updated_at: string;
  num_qubits: number | null;
  total_people: number;
}

export interface PresetInfo {
  id: string;
  name: string;
  description: string;
  num_qubits: number;
  total_people: number;
}

export interface Weights {
  distance: number;
  time: number;
  congestion: number;
  overflow: number;
}

export interface ProblemSettings {
  weights: Weights;
  paths_per_group: number;
  penalty_factor: number;
}

export interface QuantumSettings {
  reps: number;
  shots: number;
  noise: "depolarizing" | "fake_backend";
  noise_level: number;
  fake_backend: string;
  seed: number;
}

export interface Evaluation {
  energy: number;
  objective: number;
  penalty: number;
  feasible: boolean;
  components: { distance: number; time: number; congestion: number; overflow: number };
  resource_loads: Record<string, number>;
  utilisation: Record<string, number>;
  capacity_violations: number;
  people_over_capacity: number; // fewest people to remove so every route and exit fits
  total_excess: number;         // excess summed over every route and exit
  max_utilisation: number;
  total_person_distance: number;
}

export interface GroupPlan {
  group_id: string;
  size: number;
  path: string[] | null;
  exit: string | null;
  valid: boolean;
}

export interface QuantumMetrics {
  shots: number;
  prob_optimal: number;
  prob_feasible: number;
  mean_approx_ratio: number;
  random_baseline: { prob_optimal: number; prob_feasible: number; mean_approx_ratio: number };
}

export interface SolverResultDTO {
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

export interface ProblemSummary {
  venue: string;
  num_groups: number;
  num_variables: number;
  num_qubits: number;
  num_quadratic_terms: number;
  resources: { id: string; kind: "route" | "exit"; capacity: number }[];
}

export interface Quality {
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

export interface OptimizeResponse {
  problem: ProblemSummary;
  result: SolverResultDTO;
  baseline: SolverResultDTO;
  quality: Quality | null;
  /** Quantum only: the most common answer across all shots. */
  typical?: (SolverResultDTO & { probability: number }) | null;
  run_id?: number;
}

export type ExperimentKind = "scaling" | "noise" | "depth" | "versus";

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

export interface ExperimentDetail extends ExperimentInfo {
  runs: RunRow[];
}

export interface LabRunSummary {
  id: number;
  venue_name: string;
  solver: string;
  num_qubits: number;
  quality: number | null;
  created_at: string;
}

export interface LabRunDetail extends OptimizeResponse {
  id: number;
  venue: VenueDTO;
  settings: ProblemSettings;
  solver: string;
}

// ------------------------------------------------------------ IBM hardware (Stage 5)
export interface HardwareDevice {
  name: string;
  num_qubits: number;
  pending_jobs: number | null;
}

export interface HardwareCheck {
  backend: string;
  pending_jobs: number | null;
  qubits: number;
  transpiled: { depth: number; two_qubit_gates: number; [k: string]: unknown };
}

/** A job while IBM works on it. Once DONE, the response carries the full OptimizeResponse fields. */
export type HardwareJobState = {
  job_id: string;
  status: string; // SUBMITTED, QUEUED, RUNNING, DONE, ERROR, CANCELLED ...
  backend?: string;
  queue_position?: number | null;
  error?: string | null;
} & Partial<OptimizeResponse>;
