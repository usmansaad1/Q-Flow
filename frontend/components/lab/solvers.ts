// WHAT THIS FILE IS FOR: the fixed list of ways the Lab can solve a venue.
// It names each method, says if it is quantum, and sets simulator choices and size limits.
// The Lab page, solver panel, results board and run history all read from here.

// The internal names of the four solving methods the backend understands.
export type SolverKey = "classical_exact" | "qaoa_ideal" | "qaoa_noisy" | "ibm_hardware";

// The menu of solving methods, with the labels and short notes shown on screen.
// QAOA is a quantum recipe that searches for a good plan by running a short quantum program many times.
export const SOLVERS: { key: SolverKey; label: string; short: string; description: string; quantum: boolean; available: boolean }[] = [
  { key: "classical_exact", label: "Classical", short: "Classical", quantum: false, available: true,
    description: "Checks every valid plan and returns the best one." },
  { key: "qaoa_ideal", label: "QAOA simulator", short: "QAOA ideal", quantum: true, available: true,
    description: "QAOA on a perfect, error free quantum simulator." },
  { key: "qaoa_noisy", label: "Noisy QAOA", short: "QAOA noisy", quantum: true, available: true,
    description: "The same circuit with the errors of today's hardware." },
  { key: "ibm_hardware", label: "IBM quantum hardware", short: "IBM QPU", quantum: true, available: true,
    description: "A real IBM processor. Jobs wait in IBM's queue, so a run can take minutes or more." },
];

// The real IBM machines whose typical errors the noisy simulator can copy.
// The "Fake" names are IBM's built in error profiles of those machines.
export const DEVICE_MODELS = [
  { value: "FakeTorino", label: "IBM Torino (Heron, newer)" },
  { value: "FakeFez", label: "IBM Fez (Heron r2)" },
  { value: "FakeBrisbane", label: "IBM Brisbane (Eagle, older)" },
  { value: "FakeSherbrooke", label: "IBM Sherbrooke (Eagle)" },
];

// The largest problem the quantum methods are allowed to take, counted in qubits.
// A qubit is one quantum bit; here each qubit stands for one yes or no route choice.
export const QUANTUM_QUBIT_LIMIT = 16;
