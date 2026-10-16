"use client";
// WHAT THIS FILE IS FOR: a simple written list of an evacuation plan.
// For each crowd group it shows the head count and the rooms it walks through.
// The Lab page uses it under the results to spell out a chosen plan.

import type { GroupPlan } from "@/lib/types";

// Lists every group with its size and route, or says no valid route was chosen.
// The route skips the first stop, since that is the room the group starts in.
export default function PlanList({ title, plan, note }: { title: string; plan: GroupPlan[]; note?: string }) {
  return (
    <div>
      <h3 className="font-display text-base font-bold">{title}</h3>
      {note && <p className="text-xs text-ink-soft">{note}</p>}
      <ul className="mt-2 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2 xl:grid-cols-3">
        {/* One line per crowd: its size on the left, its name and route on the right */}
        {plan.map((g) => (
          <li key={g.group_id} className="flex gap-2">
            <span className="num w-12 shrink-0 text-right font-semibold">{g.size}</span>
            <span className="min-w-0">
              <span className="font-medium">{g.group_id}</span>
              <span className="block text-xs text-ink-soft">
                {g.valid && g.path ? g.path.slice(1).join(", then ") : "No valid route chosen"}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
