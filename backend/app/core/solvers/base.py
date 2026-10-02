"""Common result type returned by every solver."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.problem import RoutingProblem


@dataclass
class SolverResult:
    solver: str
    status: str                       # "optimal", "feasible", "infeasible", "error"
    bitstring: list[int]
    runtime_s: float
    evaluation: dict = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(cls, problem: RoutingProblem, solver: str, status: str, bitstring: list[int],
              runtime_s: float, **extra) -> "SolverResult":
        ev = problem.evaluate(bitstring)
        return cls(solver, status, list(map(int, bitstring)), runtime_s, ev.to_dict(), extra)

    def routes(self, problem: RoutingProblem) -> list[dict]:
        """Human readable plan: which path each group takes."""
        out = []
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
