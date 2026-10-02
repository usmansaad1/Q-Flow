"use client";

import type { GroupPlan } from "@/lib/types";

export default function PlanList({ title, plan, note }: { title: string; plan: GroupPlan[]; note?: string }) {
  return (
    <div>
      <h3 className="font-display text-base font-bold">{title}</h3>
      {note && <p className="text-xs text-ink-soft">{note}</p>}
      <ul className="mt-2 space-y-1.5 text-sm">
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
