import type { PlanLoads } from "@/components/VenueCanvas";
import type { Evaluation } from "./types";

/** Map a solver's resource loads onto canvas edges and exits. */
export function planLoads(ev: Evaluation, routeIds: Map<string, string>): PlanLoads {
  const routes = new Map<string, { load: number; util: number }>();
  routeIds.forEach((rid, edgeId) => {
    if (rid in ev.resource_loads) routes.set(edgeId, { load: ev.resource_loads[rid], util: ev.utilisation[rid] });
  });
  const exits = new Map<string, { load: number; util: number }>();
  for (const [rid, load] of Object.entries(ev.resource_loads)) {
    if (rid.startsWith("exit:")) exits.set(rid.slice(5), { load, util: ev.utilisation[rid] });
  }
  return { routes, exits };
}
