"""
The single shared formulation of the Q-Flow crowd-routing problem.

Every solver (exact, CP-SAT, QAOA ideal / noisy / hardware) works on this one
object and every answer is scored by `RoutingProblem.evaluate`, so comparisons
are always like for like.

Decision variables
------------------
x[a] = 1 if option a is chosen, where option a = (group g, candidate path j).
Qubits = sum over groups of the number of candidate paths.

Cost (all terms are quadratic in x, so no slack qubits are ever needed)
-----------------------------------------------------------------------
  H(x) = w_d * Distance + w_t * Time + w_c * Congestion + w_o * Overflow
         + A * sum_g (1 - sum_{a in g} x_a)^2              (one path per group)

  Distance   = sum_a s_a * len_a * x_a  / D_norm
  Time       = sum_a s_a * time_a * x_a / T_norm
  Congestion = (1/R) * sum_r (load_r / cap_r)^2,   load_r = sum_{a uses r} s_a x_a
  Overflow   = (1/P) * sum_r Fit_r(x)
               The true overflow max(0, load_r - cap_r) is not quadratic. For each
               resource we enumerate every feasible combination of the groups that
               can use it and least squares fit linear + pairwise coefficients to
               the true overflow. With two or fewer groups on a resource the fit is
               exact; beyond that it is the best quadratic approximation. The exact
               number of people over capacity is always reported separately.

Penalty A = penalty_factor * (naive plan cost + |sum of negative objective
coefficients|). An infeasible bitstring costs at least A plus the objective's
lowest possible value, which is strictly above the optimum, so the QUBO ground
state is always the best feasible plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from collections import defaultdict
from itertools import combinations, product
from typing import Sequence

import numpy as np

from app.core.venue import Venue, PathOption, exit_resource_id


@dataclass
class Weights:
    distance: float = 1.0
    time: float = 0.0
    congestion: float = 1.0
    overflow: float = 2.0


@dataclass
class Option:
    index: int
    name: str
    group_id: str
    group_size: int
    path: PathOption

    @property
    def resources(self) -> list[str]:
        return self.path.resources()


@dataclass
class Resource:
    id: str
    kind: str          # "route" or "exit"
    capacity: int


@dataclass
class Evaluation:
    energy: float                     # full QUBO value (objective + penalty)
    objective: float                  # weighted objective without penalty
    penalty: float
    feasible: bool
    components: dict[str, float]      # weighted contributions
    resource_loads: dict[str, int]
    utilisation: dict[str, float]
    capacity_violations: int          # resources over capacity
    people_over_capacity: int         # exact total overflow
    max_utilisation: float
    total_person_distance: float      # raw person metres
    assignment: dict[str, int | None] # group -> chosen option index within group (None if invalid)

    def to_dict(self) -> dict:
        return asdict(self)


class RoutingProblem:
    def __init__(self, venue: Venue, weights: Weights | None = None,
                 paths_per_group: int | None = 2, penalty_factor: float = 1.5):
        venue.validate()
        self.venue = venue
        self.weights = weights or Weights()
        self.paths_per_group = paths_per_group
        self.penalty_factor = penalty_factor

        self._build_options()
        self._build_resources()
        self._build_qubo()

    # ============================================================ structure
    def _build_options(self) -> None:
        self.options: list[Option] = []
        self.group_options: dict[str, list[int]] = {}
        for g in self.venue.crowd_groups:
            paths = self.venue.candidate_paths(g.location, k=self.paths_per_group)
            if not paths:
                raise ValueError(f"Group '{g.group_id}' cannot reach any exit.")
            idxs = []
            for j, p in enumerate(paths):
                idx = len(self.options)
                self.options.append(Option(idx, f"x_{g.group_id}_{j}", g.group_id, g.size, p))
                idxs.append(idx)
            self.group_options[g.group_id] = idxs

    def _build_resources(self) -> None:
        used = {r for o in self.options for r in o.resources}
        self.resources: dict[str, Resource] = {}
        for r in self.venue.routes:
            if r.id in used:
                self.resources[r.id] = Resource(r.id, "route", r.capacity)
        for e in self.venue.exits:
            rid = exit_resource_id(e.id)
            if rid in used and e.capacity:
                self.resources[rid] = Resource(rid, "exit", e.capacity)
        self.resource_users: dict[str, list[int]] = defaultdict(list)
        for o in self.options:
            for r in o.resources:
                if r in self.resources:
                    self.resource_users[r].append(o.index)

    @property
    def num_variables(self) -> int:
        return len(self.options)

    @property
    def num_qubits(self) -> int:
        return len(self.options)

    @property
    def groups(self) -> list[str]:
        return list(self.group_options.keys())

    # ============================================================== QUBO
    def _norms(self) -> tuple[float, float, int, int]:
        d_norm = sum(max(self.options[i].path.length for i in idxs) * self.options[idxs[0]].group_size
                     for idxs in self.group_options.values())
        t_norm = sum(max(self.options[i].path.travel_time for i in idxs) * self.options[idxs[0]].group_size
                     for idxs in self.group_options.values())
        return d_norm or 1.0, t_norm or 1.0, max(len(self.resources), 1), max(self.venue.total_people, 1)

    def _objective_terms(self) -> tuple[dict, dict, dict]:
        """Returns per-component (linear, quadratic) dictionaries before weighting."""
        d_norm, t_norm, n_res, n_people = self._norms()
        comp = {k: (defaultdict(float), defaultdict(float)) for k in ("distance", "time", "congestion", "overflow")}

        for o in self.options:
            comp["distance"][0][o.index] += o.group_size * o.path.length / d_norm
            comp["time"][0][o.index] += o.group_size * o.path.travel_time / t_norm

        for rid, users in self.resource_users.items():
            cap = self.resources[rid].capacity
            for a in users:
                s = self.options[a].group_size
                comp["congestion"][0][a] += (s / cap) ** 2 / n_res          # x^2 = x
            for a, b in combinations(users, 2):
                oa, ob = self.options[a], self.options[b]
                if oa.group_id == ob.group_id:
                    continue  # never both chosen in a feasible state
                comp["congestion"][1][(a, b)] += 2 * oa.group_size * ob.group_size / cap ** 2 / n_res
            lin, quad = self._fit_overflow(users, cap)
            for a, c in lin.items():
                comp["overflow"][0][a] += c / n_people
            for ab, c in quad.items():
                comp["overflow"][1][ab] += c / n_people
        return comp

    def _fit_overflow(self, users: list[int], cap: int) -> tuple[dict, dict]:
        """Least squares quadratic fit of max(0, load - cap) over all feasible
        combinations of the options that use this resource."""
        sizes = {a: self.options[a].group_size for a in users}
        if sum(sizes.values()) <= cap:
            return {}, {}                       # can never overflow
        by_group: dict[str, list[int]] = defaultdict(list)
        for a in users:
            by_group[self.options[a].group_id].append(a)
        pairs = [(a, b) for a, b in combinations(users, 2)
                 if self.options[a].group_id != self.options[b].group_id]
        cols = list(users) + pairs
        rows, target = [], []
        for combo in product(*[[None] + opts for opts in by_group.values()]):
            on = {a for a in combo if a is not None}
            rows.append([1.0 if c in on else 0.0 for c in users] +
                        [1.0 if (a in on and b in on) else 0.0 for a, b in pairs])
            target.append(max(0.0, sum(sizes[a] for a in on) - cap))
        coef, *_ = np.linalg.lstsq(np.array(rows), np.array(target), rcond=None)
        coef = np.where(np.abs(coef) < 1e-9, 0.0, coef)
        lin = {c: float(v) for c, v in zip(users, coef[: len(users)]) if v}
        quad = {ab: float(v) for ab, v in zip(pairs, coef[len(users):]) if v}
        return lin, quad

    def _build_qubo(self) -> None:
        self.components = self._objective_terms()
        w = asdict(self.weights)

        lin: dict[int, float] = defaultdict(float)
        quad: dict[tuple[int, int], float] = defaultdict(float)
        for name, (l, q) in self.components.items():
            for i, c in l.items():
                lin[i] += w[name] * c
            for ij, c in q.items():
                quad[ij] += w[name] * c
        self._obj_linear, self._obj_quadratic = dict(lin), dict(quad)

        # Penalty: strictly above any optimum (optimum <= naive plan cost).
        naive_cost = self._objective_value(self.naive_bitstring())
        neg = sum(c for c in self._obj_linear.values() if c < 0) + \
              sum(c for c in self._obj_quadratic.values() if c < 0)
        self.penalty = self.penalty_factor * max(naive_cost + abs(neg), 1e-6)

        A = self.penalty
        for idxs in self.group_options.values():
            for i in idxs:
                lin[i] += -A
            for i, j in combinations(idxs, 2):
                quad[(i, j)] += 2 * A
        self.offset = A * len(self.group_options)
        self.linear = {i: c for i, c in lin.items() if c != 0}
        self.quadratic = {ij: c for ij, c in quad.items() if c != 0}

    def _objective_value(self, x: Sequence[int]) -> float:
        v = sum(c * x[i] for i, c in self._obj_linear.items())
        v += sum(c * x[i] * x[j] for (i, j), c in self._obj_quadratic.items())
        return float(v)

    def qubo_matrix(self) -> tuple[np.ndarray, float]:
        """Upper triangular Q with linear terms on the diagonal: E = x^T Q x + offset."""
        n = self.num_variables
        Q = np.zeros((n, n))
        for i, c in self.linear.items():
            Q[i, i] += c
        for (i, j), c in self.quadratic.items():
            Q[min(i, j), max(i, j)] += c
        return Q, self.offset

    def all_energies(self, max_qubits: int = 22) -> np.ndarray:
        """QUBO energy of every bitstring. Index k encodes x_i = (k >> i) & 1."""
        n = self.num_variables
        if n > max_qubits:
            raise ValueError(f"{n} variables is too many for full enumeration.")
        ks = np.arange(2 ** n, dtype=np.int64)
        X = ((ks[:, None] >> np.arange(n)) & 1).astype(np.float64)
        Q, off = self.qubo_matrix()
        return np.einsum("ki,ij,kj->k", X, Q, X) + off

    def to_quadratic_program(self):
        """Unconstrained Qiskit QuadraticProgram (no slack variables)."""
        from qiskit_optimization import QuadraticProgram
        qp = QuadraticProgram(name=f"QFlow_{self.venue.name}".replace(" ", "_"))
        for o in self.options:
            qp.binary_var(o.name)
        names = [o.name for o in self.options]
        qp.minimize(
            constant=self.offset,
            linear={names[i]: c for i, c in self.linear.items()},
            quadratic={(names[i], names[j]): c for (i, j), c in self.quadratic.items()},
        )
        return qp

    # ========================================================= assignments
    def naive_bitstring(self) -> list[int]:
        """Baseline 'before optimisation': every group takes its shortest path."""
        x = [0] * self.num_variables
        for idxs in self.group_options.values():
            best = min(idxs, key=lambda i: self.options[i].path.length)
            x[best] = 1
        return x

    def bitstring_from_assignment(self, assignment: dict[str, int]) -> list[int]:
        x = [0] * self.num_variables
        for gid, j in assignment.items():
            x[self.group_options[gid][j]] = 1
        return x

    def is_feasible(self, x: Sequence[int]) -> bool:
        return all(sum(x[i] for i in idxs) == 1 for idxs in self.group_options.values())

    def energy(self, x: Sequence[int]) -> float:
        v = self.offset
        v += sum(c * x[i] for i, c in self.linear.items())
        v += sum(c * x[i] * x[j] for (i, j), c in self.quadratic.items())
        return float(v)

    # ============================================================ evaluate
    def evaluate(self, x: Sequence[int]) -> Evaluation:
        x = [int(b) for b in x]
        if len(x) != self.num_variables:
            raise ValueError(f"Expected {self.num_variables} bits, got {len(x)}.")
        w = asdict(self.weights)
        components = {}
        for name, (l, q) in self.components.items():
            v = sum(c * x[i] for i, c in l.items()) + sum(c * x[i] * x[j] for (i, j), c in q.items())
            components[name] = w[name] * v
        objective = sum(components.values())
        energy = self.energy(x)

        loads = {rid: sum(self.options[a].group_size for a in users if x[a])
                 for rid, users in self.resource_users.items()}
        util = {rid: loads[rid] / self.resources[rid].capacity for rid in loads}
        over = {rid: max(0, loads[rid] - self.resources[rid].capacity) for rid in loads}

        assignment = {}
        for gid, idxs in self.group_options.items():
            chosen = [j for j, i in enumerate(idxs) if x[i]]
            assignment[gid] = chosen[0] if len(chosen) == 1 else None

        return Evaluation(
            energy=energy,
            objective=objective,
            penalty=energy - objective,
            feasible=self.is_feasible(x),
            components=components,
            resource_loads=loads,
            utilisation=util,
            capacity_violations=sum(1 for v in over.values() if v > 0),
            people_over_capacity=sum(over.values()),
            max_utilisation=max(util.values()) if util else 0.0,
            total_person_distance=sum(self.options[i].group_size * self.options[i].path.length
                                      for i in range(self.num_variables) if x[i]),
            assignment=assignment,
        )

    # ============================================================== summary
    def describe(self) -> dict:
        return {
            "venue": self.venue.name,
            "num_groups": len(self.group_options),
            "num_variables": self.num_variables,
            "num_qubits": self.num_qubits,
            "num_quadratic_terms": len(self.quadratic),
            "penalty": self.penalty,
            "weights": asdict(self.weights),
            "options": [
                {"index": o.index, "name": o.name, "group_id": o.group_id, "group_size": o.group_size,
                 "nodes": o.path.nodes, "exit": o.path.exit_id, "length": o.path.length,
                 "travel_time": round(o.path.travel_time, 2)}
                for o in self.options
            ],
            "resources": [asdict(r) for r in self.resources.values()],
        }
