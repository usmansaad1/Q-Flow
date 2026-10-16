# WHAT THIS FILE IS FOR: defines the standard "answer sheet" that every solver hands back.
# Whether the plan came from a quantum or an ordinary method, it is packed the same way.
# That lets the website and the experiments compare all methods side by side.
"""Common result type returned by every solver."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.problem import RoutingProblem


# The answer sheet from one solver: its name, outcome, chosen plan and how long it took.
# The plan is a "bitstring": a row of 0s and 1s, with a 1 for each route that was picked.
# "evaluation" holds the plan's scores; "extra" holds anything specific to that solver.
@dataclass
class SolverResult:
    # Which method made the plan, such as "classical_exact" or "qaoa_noisy".
    solver: str
    status: str                       # "optimal", "feasible", "infeasible", "error"
    # The plan itself as 0s and 1s, and how many seconds the solver took.
    bitstring: list[int]
    runtime_s: float
    evaluation: dict = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    # Creates an answer sheet and scores the plan on the spot.
    # Every solver uses this, so all plans are marked by the same rules.
    @classmethod
    def build(cls, problem: RoutingProblem, solver: str, status: str, bitstring: list[int],
              runtime_s: float, **extra) -> "SolverResult":
        # Mark the plan with the shared report card from problem.py, then fill in the sheet.
        ev = problem.evaluate(bitstring)
        return cls(solver, status, list(map(int, bitstring)), runtime_s, ev.to_dict(), extra)

    # Turns the row of 0s and 1s back into a readable list: each group, its path and its exit.
    # A group is marked not valid if it ended up with no route or more than one.
    def routes(self, problem: RoutingProblem) -> list[dict]:
        """Human readable plan: which path each group takes."""
        out = []
        # For each crowd, look at its route choices and keep the ones marked 1 in the plan.
        for gid, idxs in problem.group_options.items():
            chosen = [problem.options[i] for i in idxs if self.bitstring[i]]
            out.append({
                "group_id": gid,
                "size": problem.options[idxs[0]].group_size,
                "path": chosen[0].path.nodes if len(chosen) == 1 else None,
                "exit": chosen[0].path.exit_id if len(chosen) == 1 else None,
                "valid": len(chosen) == 1,
            })
        return out

    # Packs the answer sheet into a plain dictionary, ready to send to the website.
    # If the venue problem is given, the readable route list is included too.
    def to_dict(self, problem: RoutingProblem | None = None) -> dict:
        d = {
            "solver": self.solver,
            "status": self.status,
            "bitstring": self.bitstring,
            "runtime_s": self.runtime_s,
            "objective_value": self.evaluation.get("objective"),
            "energy": self.evaluation.get("energy"),
            "evaluation": self.evaluation,
            "extra": self.extra,
        }
        if problem is not None:
            d["routes"] = self.routes(problem)
        return d
