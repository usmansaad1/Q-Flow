# WHAT THIS FILE IS FOR: the scoring formula at the heart of Q-Flow.
# It turns "which escape route should each crowd take?" into one score to make as low as possible.
# Every solver, classical or quantum, is judged by this same score, so the comparison is fair.
# It also produces the "report card" for any plan: crowding, people over capacity, distance walked.
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
from scipy.optimize import linprog

from app.core.venue import Venue, PathOption, exit_resource_id


# How much each of the four score parts matters. Bigger number, more importance.
# By default distance and crowding count equally, overflow counts double and travel time is ignored.
@dataclass
class Weights:
    distance: float = 1.0
    time: float = 0.0
    congestion: float = 1.0
    overflow: float = 2.0


# One yes or no choice in the puzzle: "crowd G takes escape route J".
# Each Option becomes one qubit (the basic memory unit of a quantum computer) or one switch.
@dataclass
class Option:
    # Its position in the full list of choices, which is also its qubit number.
    index: int
    # A readable label such as "x_Balcony_1" (crowd Balcony, its route number 1).
    name: str
    # Which crowd this choice belongs to, and how many people are in it.
    group_id: str
    group_size: int
    # The escape route itself, from venue.py.
    path: PathOption

    # The walkways and exit door this choice would use.
    @property
    def resources(self) -> list[str]:
        return self.path.resources()


# Anything with limited room that crowds share: a walkway or an exit door, with its capacity.
@dataclass
class Resource:
    id: str
    kind: str          # "route" or "exit"
    capacity: int


# The report card for one plan: its total score, each score part, whether it follows the
# one route per group rule, how full each walkway and exit is, and how many people do not fit.
@dataclass
class Evaluation:
    energy: float                 # the full score, penalty included (lower is better)
    objective: float              # the score without the penalty
    penalty: float                # how much was added for breaking the rule
    feasible: bool                # True if every crowd has exactly one route
    components: dict              # each of the four parts, after weighting
    resource_loads: dict          # people on each route and exit
    utilisation: dict             # how full each one is (1.0 = exactly full)
    capacity_violations: int      # how many routes and exits are over capacity
    people_over_capacity: int     # fewest people to remove so everything fits
    total_excess: int             # excess added up over every spot (counts people twice)
    max_utilisation: float        # the fullest route or exit
    total_person_distance: float  # people × metres walked, added up
    assignment: dict              # which route number each crowd picked (None if invalid)

    # Converts the report card into plain data so it can be sent to the website.
    def to_dict(self) -> dict:
        return asdict(self)


# The full routing puzzle for one venue. Built once, then shared by every solver.
# It lists the choices, the walkways and exits they share, and the scoring formula itself.
# The formula is stored as a QUBO: a standard puzzle format for quantum solvers,
# made of yes or no switches with a cost for each switch and for each pair of switches.
class RoutingProblem:
    # Sets up the puzzle: checks the venue, then builds the choices, the shared resources and the formula.
    # paths_per_group is how many escape routes each crowd may pick from.
    # penalty_factor controls how strongly the one route per group rule is enforced.
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
    # ROUTE CHOICES: works out the escape routes each crowd may choose from.
    # First it imagines every crowd taking its shortest route, to see which walkways would be busy.
    # Then it asks the venue for each crowd's choices, steering any extra detours away from busy spots.
    def _build_options(self) -> None:
        self.options: list[Option] = []
        self.group_options: dict[str, list[int]] = {}
        # Expected loads if every group took its shortest route; used to pick detours
        # around crowded roads when more than one route per exit is considered.
        loads: dict[str, int] = defaultdict(int)
        shortest: dict[str, set[str]] = {}
        for g in self.venue.crowd_groups:
            first = self.venue.candidate_paths(g.location, k=1)
            shortest[g.group_id] = set(first[0].resources()) if first else set()
            for rid in shortest[g.group_id]:
                loads[rid] += g.size
        for g in self.venue.crowd_groups:
            paths = self.venue.candidate_paths(g.location, k=self.paths_per_group, loads=loads,
                                               size=g.size, own=shortest[g.group_id])
            if not paths:
                raise ValueError(f"{g.location} can't reach any exit. Add a route from it, "
                                 f"or from a place it connects to, to an exit.")
            # Number each choice and remember which crowd it belongs to, e.g. "x_Balcony_1".
            idxs = []
            for j, p in enumerate(paths):
                idx = len(self.options)
                self.options.append(Option(idx, f"x_{g.group_id}_{j}", g.group_id, g.size, p))
                idxs.append(idx)
            self.group_options[g.group_id] = idxs

    # Lists every walkway and exit that at least one choice uses, with its capacity.
    # Exits without a stated capacity are left out, as they can never be overloaded.
    # Also records, for each walkway or exit, which choices pass through it.
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

    # How many yes or no choices the puzzle has in total.
    @property
    def num_variables(self) -> int:
        return len(self.options)

    # How many qubits a quantum computer needs: one per choice, with no extra helper qubits.
    @property
    def num_qubits(self) -> int:
        return len(self.options)

    # The names of all crowds, in order.
    @property
    def groups(self) -> list[str]:
        return list(self.group_options.keys())

    # ============================================================== QUBO
    # Works out the "worst case" numbers used to scale each score part to a similar size.
    # Distance and time: every crowd taking its longest choice. Also the number of resources and people.
    # Without this, a score part measured in metres would swamp one measured in fractions.
    def _norms(self) -> tuple[float, float, int, int]:
        d_norm = sum(max(self.options[i].path.length for i in idxs) * self.options[idxs[0]].group_size
                     for idxs in self.group_options.values())
        t_norm = sum(max(self.options[i].path.travel_time for i in idxs) * self.options[idxs[0]].group_size
                     for idxs in self.group_options.values())
        return d_norm or 1.0, t_norm or 1.0, max(len(self.resources), 1), max(self.venue.total_people, 1)

    # THE FOUR SCORE PARTS: distance, time, congestion (crowding) and overflow.
    # Each part is stored as costs for single choices plus extra costs for pairs of choices.
    # A pair cost only applies when both choices in the pair are picked together.
    def _objective_terms(self) -> tuple[dict, dict, dict]:
        """Returns per-component (linear, quadratic) dictionaries before weighting."""
        d_norm, t_norm, n_res, n_people = self._norms()
        comp = {k: (defaultdict(float), defaultdict(float)) for k in ("distance", "time", "congestion", "overflow")}

        # Parts 1 and 2, distance and time: each choice costs its crowd size times its length
        # (or walking time), scaled by the worst case. So walking 300 people 20 metres costs
        # more than walking 100 people the same way.
        for o in self.options:
            comp["distance"][0][o.index] += o.group_size * o.path.length / d_norm
            comp["time"][0][o.index] += o.group_size * o.path.travel_time / t_norm

        # Part 3, congestion: for every walkway and exit, how full it is (people divided by
        # capacity), squared, then averaged. Squaring makes a very full spot cost far more
        # than two half full ones. Written out, this gives a cost for each crowd on its own,
        # plus an extra cost whenever two different crowds share the same spot.
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
            # Part 4, overflow: roughly how many people exceed this spot's capacity,
            # using the approximation from _fit_overflow, divided by the total number of people.
            lin, quad = self._fit_overflow(users, cap)
            for a, c in lin.items():
                comp["overflow"][0][a] += c / n_people
            for ab, c in quad.items():
                comp["overflow"][1][ab] += c / n_people
        return comp

    # THE OVERFLOW APPROXIMATION for one walkway or exit.
    # The true rule "people over capacity, or zero if it fits" cannot be written using only
    # single and pair costs, which is all a QUBO allows. So this finds the single and pair
    # costs that come closest to the true rule, judged across every possible combination.
    def _fit_overflow(self, users: list[int], cap: int) -> tuple[dict, dict]:
        """Least squares quadratic fit of max(0, load - cap) over all feasible
        combinations of the options that use this resource."""
        sizes = {a: self.options[a].group_size for a in users}
        if sum(sizes.values()) <= cap:
            return {}, {}                       # can never overflow
        # Step 1: sort the choices using this spot by crowd, and list every pair of
        # choices from two different crowds. These are the costs we will solve for.
        by_group: dict[str, list[int]] = defaultdict(list)
        for a in users:
            by_group[self.options[a].group_id].append(a)
        pairs = [(a, b) for a, b in combinations(users, 2)
                 if self.options[a].group_id != self.options[b].group_id]
        cols = list(users) + pairs
        # Step 2: try every combination where each crowd uses this spot by one of its choices,
        # or not at all. For each, note which costs would apply and the true overflow.
        rows, target = [], []
        for combo in product(*[[None] + opts for opts in by_group.values()]):
            on = {a for a in combo if a is not None}
            rows.append([1.0 if c in on else 0.0 for c in users] +
                        [1.0 if (a in on and b in on) else 0.0 for a, b in pairs])
            target.append(max(0.0, sum(sizes[a] for a in on) - cap))
        # Step 3: find the costs that best match the true overflow over all combinations
        # ("least squares": the smallest total of squared mistakes). Tiny values become zero.
        coef, *_ = np.linalg.lstsq(np.array(rows), np.array(target), rcond=None)
        coef = np.where(np.abs(coef) < 1e-9, 0.0, coef)
        lin = {c: float(v) for c, v in zip(users, coef[: len(users)]) if v}
        quad = {ab: float(v) for ab, v in zip(pairs, coef[len(users):]) if v}
        return lin, quad

    # Assembles the final formula: the four score parts mixed by their weights,
    # plus a heavy penalty for breaking the one route per group rule.
    def _build_qubo(self) -> None:
        self.components = self._objective_terms()
        w = asdict(self.weights)

        # Step 1: add the four parts together, each multiplied by its weight.
        # "lin" holds the cost of each single choice; "quad" holds the extra cost of each pair.
        lin: dict[int, float] = defaultdict(float)
        quad: dict[tuple[int, int], float] = defaultdict(float)
        for name, (l, q) in self.components.items():
            for i, c in l.items():
                lin[i] += w[name] * c
            for ij, c in q.items():
                quad[ij] += w[name] * c
        self._obj_linear, self._obj_quadratic = dict(lin), dict(quad)

        # Step 2: choose the penalty size. It is set larger than the cost of the simple
        # "everyone takes the shortest route" plan, so cheating the rule never pays off.
        # Penalty: strictly above any optimum (optimum <= naive plan cost).
        naive_cost = self._objective_value(self.naive_bitstring())
        neg = sum(c for c in self._obj_linear.values() if c < 0) + \
              sum(c for c in self._obj_quadratic.values() if c < 0)
        self.penalty = self.penalty_factor * max(naive_cost + abs(neg), 1e-6)

        # Step 3, THE ONE ROUTE PER GROUP PENALTY: penalty times (1 minus the number of routes
        # picked for the crowd), squared. Exactly one route gives zero; none or two gives a penalty.
        # Written out: each choice earns a minus penalty, each pair from the same crowd a double
        # penalty, plus a fixed penalty per crowd kept in the "offset".
        A = self.penalty
        for idxs in self.group_options.values():
            for i in idxs:
                lin[i] += -A
            for i, j in combinations(idxs, 2):
                quad[(i, j)] += 2 * A
        self.offset = A * len(self.group_options)
        self.linear = {i: c for i, c in lin.items() if c != 0}
        self.quadratic = {ij: c for ij, c in quad.items() if c != 0}

    # Scores a plan using only the four weighted parts, ignoring the penalty.
    # x is the plan written as a list of 1s (picked) and 0s (not picked), one per choice.
    def _objective_value(self, x: Sequence[int]) -> float:
        v = sum(c * x[i] for i, c in self._obj_linear.items())
        v += sum(c * x[i] * x[j] for (i, j), c in self._obj_quadratic.items())
        return float(v)

    # Writes the whole formula as a square table of numbers (a matrix), plus a fixed offset.
    # Single choice costs sit on the diagonal; pair costs sit above it.
    def qubo_matrix(self) -> tuple[np.ndarray, float]:
        """Upper triangular Q with linear terms on the diagonal: E = x^T Q x + offset."""
        n = self.num_variables
        Q = np.zeros((n, n))
        for i, c in self.linear.items():
            Q[i, i] += c
        for (i, j), c in self.quadratic.items():
            Q[min(i, j), max(i, j)] += c
        return Q, self.offset

    # Scores every possible plan at once, valid or not, by brute force.
    # Only allowed for small puzzles (22 choices or fewer), since the count doubles with each choice.
    # Used to find the true best answer and to rank what the quantum solver found.
    def all_energies(self, max_qubits: int = 22) -> np.ndarray:
        """QUBO energy of every bitstring. Index k encodes x_i = (k >> i) & 1."""
        n = self.num_variables
        if n > max_qubits:
            raise ValueError(f"{n} variables is too many for full enumeration.")
        # Step 1: number every possible plan 0, 1, 2, ... and spell each number out as 1s and 0s.
        # For example with 3 choices, plan number 5 is 1, 0, 1 (choices 0 and 2 picked).
        ks = np.arange(2 ** n, dtype=np.int64)
        X = ((ks[:, None] >> np.arange(n)) & 1).astype(np.float64)
        # Step 2: score all plans in one go using the table of numbers from qubo_matrix.
        Q, off = self.qubo_matrix()
        return np.einsum("ki,ij,kj->k", X, Q, X) + off

    # Hands the same formula to Qiskit, IBM's quantum programming toolkit, in its own format.
    # The quantum solvers start from this.
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
    # The "before" plan used for comparison: every crowd simply takes its shortest route.
    def naive_bitstring(self) -> list[int]:
        """Baseline 'before optimisation': every group takes its shortest path."""
        x = [0] * self.num_variables
        for idxs in self.group_options.values():
            best = min(idxs, key=lambda i: self.options[i].path.length)
            x[best] = 1
        return x

    # Turns a plan written as "crowd name: route number" into the list of 1s and 0s.
    def bitstring_from_assignment(self, assignment: dict[str, int]) -> list[int]:
        x = [0] * self.num_variables
        for gid, j in assignment.items():
            x[self.group_options[gid][j]] = 1
        return x

    # Checks the plan obeys the rule: every crowd has picked exactly one route.
    def is_feasible(self, x: Sequence[int]) -> bool:
        return all(sum(x[i] for i in idxs) == 1 for idxs in self.group_options.values())

    # The plan's full score ("energy" in quantum terms), including any rule breaking penalty.
    # Lower is better.
    def energy(self, x: Sequence[int]) -> float:
        v = self.offset
        v += sum(c * x[i] for i, c in self.linear.items())
        v += sum(c * x[i] * x[j] for (i, j), c in self.quadratic.items())
        return float(v)

    # ============================================================ evaluate
    # THE REPORT CARD: grades any plan in the same way, whichever solver produced it.
    # Gives the score and its parts, plus real world measures such as people over capacity.
    def evaluate(self, x: Sequence[int]) -> Evaluation:
        # Step 1: tidy the plan into 1s and 0s and check it has the right length.
        x = [int(b) for b in x]
        if len(x) != self.num_variables:
            raise ValueError(f"Expected {self.num_variables} bits, got {len(x)}.")
        # Step 2: work out each weighted score part, the total without penalty, and the full score.
        w = asdict(self.weights)
        components = {}
        for name, (l, q) in self.components.items():
            v = sum(c * x[i] for i, c in l.items()) + sum(c * x[i] * x[j] for (i, j), c in q.items())
            components[name] = w[name] * v
        objective = sum(components.values())
        energy = self.energy(x)

        # Step 3: count the actual people on each walkway and exit, how full each is,
        # and how many people over capacity each one is.
        loads = {rid: sum(self.options[a].group_size for a in users if x[a])
                 for rid, users in self.resource_users.items()}
        util = {rid: loads[rid] / self.resources[rid].capacity for rid in loads}
        over = {rid: max(0, loads[rid] - self.resources[rid].capacity) for rid in loads}

        # Step 4: note which route number each crowd picked, or None if it picked none or several.
        assignment = {}
        for gid, idxs in self.group_options.items():
            chosen = [j for j, i in enumerate(idxs) if x[i]]
            assignment[gid] = chosen[0] if len(chosen) == 1 else None

        # Step 5: fill in the report card. The penalty is whatever the full score adds
        # on top of the four parts; total person distance is people times metres walked.
        return Evaluation(
            energy=energy,
            objective=objective,
            penalty=energy - objective,
            feasible=self.is_feasible(x),
            components=components,
            resource_loads=loads,
            utilisation=util,
            capacity_violations=sum(1 for v in over.values() if v > 0),
            people_over_capacity=self._people_over_capacity(x, loads),
            total_excess=sum(over.values()),
            max_utilisation=max(util.values()) if util else 0.0,
            total_person_distance=sum(self.options[i].group_size * self.options[i].path.length
                                      for i in range(self.num_variables) if x[i]),
            assignment=assignment,
        )

    # Counts how many people genuinely do not fit, without counting anyone twice.
    # Uses a small linear programme (a standard maths method for finding the best value under limits).
    def _people_over_capacity(self, x: Sequence[int], loads: dict[str, int]) -> int:
        """
        The fewest people who would have to be taken out of the plan so that every
        route and exit is within capacity.

        Simply adding up the excess on every route and exit counts the same people
        repeatedly: 280 extra people on a corridor and the gate it leads to are the
        same 280 people, not 560. Taking the largest single excess fails the other way
        when two separate gates are overloaded by different people. This small linear
        programme answers the question exactly in both cases.
        """
        # Step 1: find the walkways and exits that are over capacity. If none, nobody is over.
        overloaded = [rid for rid, load in loads.items() if load > self.resources[rid].capacity]
        if not overloaded:
            return 0
        # Step 2: set up the question "remove as few people as possible from the chosen routes
        # so that every overloaded spot fits". Each overloaded spot gives one limit.
        chosen = [a for a in range(self.num_variables) if x[a]]
        # Variable r_a = people removed from chosen option a, between 0 and its group size.
        A_ub = [[-1.0 if a in self.resource_users[rid] else 0.0 for a in chosen] for rid in overloaded]
        b_ub = [self.resources[rid].capacity - loads[rid] for rid in overloaded]
        # Step 3: let SciPy's solver answer it, then round up to whole people.
        res = linprog(c=np.ones(len(chosen)), A_ub=A_ub, b_ub=b_ub,
                      bounds=[(0, self.options[a].group_size) for a in chosen], method="highs")
        if not res.success:  # cannot happen (removing everyone always works), but never hide overflow
            return int(sum(loads[r] - self.resources[r].capacity for r in overloaded))
        return int(np.ceil(res.fun - 1e-9))

    # ============================================================== summary
    # A plain summary of the puzzle for the website: its size, penalty, weights,
    # every route choice with its places and length, and every walkway and exit with its capacity.
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
