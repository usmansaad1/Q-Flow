export const pct = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v) ? "n/a" : `${(v * 100).toFixed(digits)}%`;

export const num = (v: number | null | undefined, digits = 2) =>
  v == null || Number.isNaN(v) ? "n/a" : v.toFixed(digits);

export function seconds(v: number | null | undefined): string {
  if (v == null) return "n/a";
  if (v < 0.001) return `${(v * 1e6).toFixed(0)} µs`;
  if (v < 1) return `${(v * 1000).toFixed(v < 0.01 ? 1 : 0)} ms`;
  return `${v.toFixed(1)} s`;
}

/** Congestion colour scale shared by the venue plan and the legend. */
export const LOAD_BANDS = [
  { max: 0, color: "#C9D1DC", label: "Unused" },
  { max: 0.6, color: "#00894B", label: "Under 60%" },
  { max: 0.85, color: "#E2A11B", label: "60 to 85%" },
  { max: 1.0, color: "#D9482B", label: "85 to 100%" },
  { max: Infinity, color: "#7A1F3D", label: "Over capacity" },
] as const;

export function loadColor(util: number | undefined): string {
  if (util == null || util <= 0) return LOAD_BANDS[0].color;
  return LOAD_BANDS.find((b) => util <= b.max)!.color;
}
