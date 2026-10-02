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
  people_over_capacity: number;
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
    timing?: { training_s: number; execution_s: number; total_s: number };
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
