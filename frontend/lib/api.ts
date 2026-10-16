// WHAT THIS FILE IS FOR: the website's messenger to the backend server, which does the maths.
// Every page calls the functions here to load venues, run solvers and start experiments.
// The server is reached through an API: a set of web addresses that accept and return data.
import type {
  ExperimentDetail, ExperimentInfo, ExperimentKind, OptimizeResponse, PresetInfo,
  ProblemSettings, ProblemSummary, QuantumSettings, SavedVenueSummary, VenueDTO, LabRunSummary, LabRunDetail,
  HardwareCheck, HardwareDevice, HardwareJobState,
} from "./types";

// The server's web address. It can be set in the environment; otherwise this computer is assumed.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

// An error from the server, carrying a readable message and the server's status number.
export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

// Sends one message to the server and returns its reply.
// If the server is off or refuses, it raises an error with a plain message for the screen.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  // Step 1: send the message; if nothing answers, explain how to start the server.
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      `Can't reach the Q-Flow backend at ${API_URL}. Start it from the backend folder with: uvicorn app.main:app --reload`,
    );
  }
  // Step 2: an empty reply (for example after a delete) means there is nothing to return.
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  // Step 3: if the server refused, turn its error details into one readable message.
  if (!res.ok) {
    const detail = body?.detail;
    const msg = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d: { msg?: string }) => d.msg).join("; ")
      : `Request failed (${res.status})`;
    throw new ApiError(msg, res.status);
  }
  return body as T;
}

// The full list of things the website can ask the server to do, one function per request.
// JSON, used below, is a plain text format for sending data over the web.
export const api = {
  // Fetches the list of ready made example venues.
  presets: () => request<PresetInfo[]>("/api/v1/presets"),
  // Fetches one example venue in full, by its id.
  preset: (id: string) => request<VenueDTO>(`/api/v1/presets/${id}`),
  // Fetches the list of venues the user has saved.
  savedVenues: () => request<SavedVenueSummary[]>("/api/v1/venues"),
  // Fetches one saved venue in full, by its number.
  savedVenue: (id: number) => request<VenueDTO>(`/api/v1/venues/${id}`),
  // Saves a new venue on the server.
  saveVenue: (venue: VenueDTO) =>
    request<SavedVenueSummary>("/api/v1/venues", { method: "POST", body: JSON.stringify({ venue }) }),
  // Overwrites an existing saved venue with the edited version.
  updateVenue: (id: number, venue: VenueDTO) =>
    request<SavedVenueSummary>(`/api/v1/venues/${id}`, { method: "PUT", body: JSON.stringify({ venue }) }),
  // Deletes a saved venue.
  deleteVenue: (id: number) => request<void>(`/api/v1/venues/${id}`, { method: "DELETE" }),
  // Asks how big the maths problem for this venue would be, without solving it.
  problem: (venue: VenueDTO, settings: ProblemSettings) =>
    request<ProblemSummary>("/api/v1/problem", { method: "POST", body: JSON.stringify({ venue, settings }) }),
  // Solves the venue with the chosen solver and returns the plan and its scores.
  // Quantum settings are sent only when a quantum solver is chosen.
  /** record = false for display only solves (the Overview demo), which stay out of Run history. */
  optimize: (venue: VenueDTO, settings: ProblemSettings, solver: string, quantum?: QuantumSettings, record = true) =>
    request<OptimizeResponse>("/api/v1/optimize", {
      method: "POST",
      body: JSON.stringify({ venue, settings, solver, record, ...(quantum ? { quantum } : {}) }),
    }),
  // Fetches the list of past runs for the run history.
  labRuns: () => request<LabRunSummary[]>("/api/v1/lab-runs"),
  // Fetches one past run in full, so it can be shown again.
  labRun: (id: number) => request<LabRunDetail>(`/api/v1/lab-runs/${id}`),
  // Deletes one past run from the history.
  deleteLabRun: (id: number) => request<void>(`/api/v1/lab-runs/${id}`, { method: "DELETE" }),
  // Fetches the list of experiments.
  experiments: () => request<ExperimentInfo[]>("/api/v1/experiments"),
  // Fetches one experiment with all its result rows.
  experiment: (id: number) => request<ExperimentDetail>(`/api/v1/experiments/${id}`),
  // Starts a new experiment of the chosen kind; "quick" runs a smaller, faster version.
  startExperiment: (kind: ExperimentKind, quick: boolean) =>
    request<{ id: number; status: string }>("/api/v1/experiments", {
      method: "POST", body: JSON.stringify({ kind, quick }),
    }),
  // Deletes an experiment and its results.
  deleteExperiment: (id: number) => request<void>(`/api/v1/experiments/${id}`, { method: "DELETE" }),
  // Builds the web address of an experiment's chart picture made by the server.
  chartUrl: (id: number) => `${API_URL}/api/v1/experiments/${id}/chart`,
  // IBM hardware: the backend reads the IBM key from its own environment, never from the browser.
  // Fetches the list of real IBM quantum computers available.
  hardwareDevices: () => request<HardwareDevice[]>("/api/v1/hardware/devices"),
  // Does a trial preparation for IBM hardware without sending the job, to show size and queue.
  hardwareDryRun: (venue: VenueDTO, settings: ProblemSettings, quantum: QuantumSettings, device: string | null) =>
    request<HardwareCheck>("/api/v1/hardware/dry-run", {
      method: "POST", body: JSON.stringify({ venue, settings, quantum, device }),
    }),
  // Sends a real job to an IBM quantum computer and returns its job number.
  hardwareSubmit: (venue: VenueDTO, settings: ProblemSettings, quantum: QuantumSettings, device: string | null) =>
    request<{ job_id: string; backend: string; status: string }>("/api/v1/hardware/jobs", {
      method: "POST", body: JSON.stringify({ venue, settings, quantum, device }),
    }),
  // Checks on a submitted IBM job; once it is done, the reply includes the results.
  hardwareJob: (jobId: string) => request<HardwareJobState>(`/api/v1/hardware/jobs/${jobId}`),
};
