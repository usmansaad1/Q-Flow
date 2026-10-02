export type SolverKey = "classical_exact" | "qaoa_ideal" | "qaoa_noisy" | "ibm_hardware";

export const SOLVERS: { key: SolverKey; label: string; short: string; description: string; quantum: boolean; available: boolean }[] = [
  { key: "classical_exact", label: "Classical", short: "Classical", quantum: false, available: true,
    description: "Checks every valid plan and returns the best one." },
  { key: "qaoa_ideal", label: "QAOA simulator", short: "QAOA ideal", quantum: true, available: true,
    description: "QAOA on a perfect, error free quantum simulator." },
  { key: "qaoa_noisy", label: "Noisy QAOA", short: "QAOA noisy", quantum: true, available: true,
    description: "The same circuit with the errors of today's hardware." },
  { key: "ibm_hardware", label: "IBM quantum hardware", short: "IBM QPU", quantum: true, available: false,
    description: "A real IBM processor. Arrives in Stage 5." },
];

export const DEVICE_MODELS = [
  { value: "FakeTorino", label: "IBM Torino (Heron, newer)" },
  { value: "FakeFez", label: "IBM Fez (Heron r2)" },
  { value: "FakeBrisbane", label: "IBM Brisbane (Eagle, older)" },
  { value: "FakeSherbrooke", label: "IBM Sherbrooke (Eagle)" },
];

export const QUANTUM_QUBIT_LIMIT = 16;
