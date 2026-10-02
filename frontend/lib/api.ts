import type {
  ExperimentDetail, ExperimentInfo, ExperimentKind, OptimizeResponse, PresetInfo,
  ProblemSettings, ProblemSummary, QuantumSettings, VenueDTO,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
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
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const msg = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d: { msg?: string }) => d.msg).join("; ")
      : `Request failed (${res.status})`;
    throw new ApiError(msg, res.status);
  }
  return body as T;
}

export const api = {
  presets: () => request<PresetInfo[]>("/api/v1/presets"),
  preset: (id: string) => request<VenueDTO>(`/api/v1/presets/${id}`),
  problem: (venue: VenueDTO, settings: ProblemSettings) =>
    request<ProblemSummary>("/api/v1/problem", { method: "POST", body: JSON.stringify({ venue, settings }) }),
  optimize: (venue: VenueDTO, settings: ProblemSettings, solver: string, quantum?: QuantumSettings) =>
    request<OptimizeResponse>("/api/v1/optimize", {
      method: "POST",
      body: JSON.stringify({ venue, settings, solver, ...(quantum ? { quantum } : {}) }),
    }),
  experiments: () => request<ExperimentInfo[]>("/api/v1/experiments"),
  experiment: (id: number) => request<ExperimentDetail>(`/api/v1/experiments/${id}`),
  startExperiment: (kind: ExperimentKind, quick: boolean) =>
    request<{ id: number; status: string }>("/api/v1/experiments", {
      method: "POST", body: JSON.stringify({ kind, quick }),
    }),
  deleteExperiment: (id: number) => request<void>(`/api/v1/experiments/${id}`, { method: "DELETE" }),
  chartUrl: (id: number) => `${API_URL}/api/v1/experiments/${id}/chart`,
};
