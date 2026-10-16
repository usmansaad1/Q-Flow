// WHAT THIS FILE IS FOR: small helpers that turn raw numbers into tidy text for the screen.
// Pages use them for percentages, times and the traffic light colours of crowded routes.

// Shows a fraction as a percentage, for example 0.42 becomes "42%". Missing values show "n/a".
export const pct = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v) ? "n/a" : `${(v * 100).toFixed(digits)}%`;

// Shows a number rounded to a set number of decimal places. Missing values show "n/a".
export const num = (v: number | null | undefined, digits = 2) =>
  v == null || Number.isNaN(v) ? "n/a" : v.toFixed(digits);

// Shows a time in the most readable unit: microseconds, milliseconds or seconds.
export function seconds(v: number | null | undefined): string {
  if (v == null) return "n/a";
  if (v < 0.001) return `${(v * 1e6).toFixed(0)} µs`;
  if (v < 1) return `${(v * 1000).toFixed(v < 0.01 ? 1 : 0)} ms`;
  return `${v.toFixed(1)} s`;
}

// Grey for unused, green for comfortable, amber and red as it fills, dark red when over capacity.
/** Congestion colour scale shared by the venue plan and the legend. */
export const LOAD_BANDS = [
  { max: 0, color: "#C9D1DC", label: "Unused" },
  { max: 0.6, color: "#00894B", label: "Under 60%" },
  { max: 0.85, color: "#E2A11B", label: "60 to 85%" },
  { max: 1.0, color: "#D9482B", label: "85 to 100%" },
  { max: Infinity, color: "#7A1F3D", label: "Over capacity" },
] as const;

// Picks the colour for a route or exit from how full it is, using the bands above.
export function loadColor(util: number | undefined): string {
  if (util == null || util <= 0) return LOAD_BANDS[0].color;
  return LOAD_BANDS.find((b) => util <= b.max)!.color;
}
