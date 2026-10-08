"""
Guarantees the quantum stage depends on. If any of these fail, quantum vs
classical comparisons are not trustworthy.
"""
import random
import warnings

import numpy as np
import pytest

warnings.filterwarnings("ignore")

from app.core.presets import PRESETS, get_preset
from app.core.problem import RoutingProblem, Weights
from app.core.solvers import solve_exact, solve_cpsat, solve_naive
from app.core.venue import Venue

PRESET_IDS = list(PRESETS)


@pytest.fixture(params=PRESET_IDS)
def problem(request):
    return RoutingProblem(get_preset(request.param))


def test_qubit_counts_match_experiment_plan():
    counts = {pid: RoutingProblem(get_preset(pid)).num_qubits for pid in PRESET_IDS}
    assert counts == {"micro_hall": 4, "small_event_hall": 6, "concert_venue": 8, "exhibition_centre": 10}


def test_qubo_ground_state_is_exact_optimum(problem):
    """Brute force over ALL 2^n bitstrings, infeasible ones included."""
    energies = problem.all_energies()
    exact = solve_exact(problem)
    assert energies.min() == pytest.approx(exact.extra["optimal_energy"], abs=1e-9)
    ground = int(np.argmin(energies))
    bits = [(ground >> i) & 1 for i in range(problem.num_variables)]
    assert problem.is_feasible(bits)


def test_every_infeasible_state_is_worse_than_optimum(problem):
    energies = problem.all_energies()
    opt = solve_exact(problem).extra["optimal_energy"]
    n = problem.num_variables
    for k, e in enumerate(energies):
        bits = [(k >> i) & 1 for i in range(n)]
        if not problem.is_feasible(bits):
            assert e > opt


def test_energy_matrix_and_evaluator_agree(problem):
    energies = problem.all_energies()
    rng = random.Random(0)
    for _ in range(50):
        k = rng.randrange(len(energies))
        bits = [(k >> i) & 1 for i in range(problem.num_variables)]
        ev = problem.evaluate(bits)
        assert ev.energy == pytest.approx(energies[k], abs=1e-9)
        assert ev.energy == pytest.approx(ev.objective + ev.penalty, abs=1e-9)
        if ev.feasible:
            assert ev.penalty == pytest.approx(0, abs=1e-9)


def test_cpsat_matches_exact(problem):
    assert solve_cpsat(problem).evaluation["energy"] == pytest.approx(
        solve_exact(problem).evaluation["energy"], abs=1e-6)


def test_optimisation_never_worse_than_naive(problem):
    assert solve_exact(problem).evaluation["energy"] <= solve_naive(problem).evaluation["energy"] + 1e-12


def test_optimum_removes_capacity_violations_on_presets(problem):
    assert solve_naive(problem).evaluation["capacity_violations"] > 0
    assert solve_exact(problem).evaluation["capacity_violations"] == 0


def test_paths_never_pass_through_an_exit(problem):
    exits = {e.id for e in problem.venue.exits}
    for o in problem.options:
        assert o.path.nodes[-1] in exits
        assert not exits.intersection(o.path.nodes[:-1])


def test_overflow_fit_is_exact_for_two_groups():
    v = Venue("two")
    v.add_location("A", "zone").add_location("B", "zone").add_location("E", "exit")
    v.add_route("A", "E", capacity=100, length=10).add_route("B", "E", capacity=100, length=10)
    v.add_route("A", "B", capacity=500, length=50)
    v.add_group("g1", "A", 80).add_group("g2", "B", 70)
    p = RoutingProblem(v, Weights(distance=0, time=0, congestion=0, overflow=1), paths_per_group=1)
    # Both groups end at exit E (no capacity set) and do not share a route: no overflow.
    assert p.evaluate([1, 1]).components["overflow"] == pytest.approx(0)
    v.locations[2].capacity = 100
    p = RoutingProblem(v, Weights(distance=0, time=0, congestion=0, overflow=1), paths_per_group=1)
    # 150 people through a 100 capacity exit: exactly 50 over, normalised by 150 people.
    assert p.evaluate([1, 1]).components["overflow"] == pytest.approx(50 / 150, abs=1e-9)


def test_round_trip_serialisation():
    v = get_preset("concert_venue")
    v2 = Venue.from_dict(v.to_dict())
    assert RoutingProblem(v).linear == pytest.approx(RoutingProblem(v2).linear)


def test_validation_rejects_bad_venues():
    v = Venue("bad").add_location("A", "zone")
    with pytest.raises(ValueError):
        RoutingProblem(v)


def test_qiskit_export_matches_internal_qubo(problem):
    qp = problem.to_quadratic_program()
    assert qp.get_num_vars() == problem.num_qubits          # no slack variables added
    assert qp.get_num_linear_constraints() == 0
    rng = random.Random(1)
    for _ in range(20):
        bits = [rng.randint(0, 1) for _ in range(problem.num_variables)]
        assert qp.objective.evaluate(bits) == pytest.approx(problem.energy(bits), abs=1e-9)


def test_api_round_trip():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert len(c.get("/api/v1/presets").json()) == len(PRESETS)
    venue = c.get("/api/v1/presets/small_event_hall").json()
    r = c.post("/api/v1/optimize", json={"venue": venue, "solver": "classical_cpsat"})
    assert r.status_code == 200
    body = r.json()
    assert body["quality"]["is_optimal"]
    assert 0 <= body["quality"]["baseline_approx_ratio"] < 1   # nearest exit plan is not optimal here
    assert body["result"]["evaluation"]["capacity_violations"] == 0
    assert body["baseline"]["evaluation"]["capacity_violations"] > 0
    assert c.post("/api/v1/optimize", json={"preset_id": "micro_hall", "solver": "ibm_hardware"}).status_code == 501


def _two_exit_venue(size_a, size_b, gate_a_cap, gate_b_cap, corridor_cap):
    """Zone A reaches Gate A only through a corridor; zone B goes straight to Gate B."""
    v = Venue("over")
    v.add_location("A", "zone").add_location("B", "zone").add_location("Corridor", "corridor")
    v.add_location("Gate A", "exit", capacity=gate_a_cap).add_location("Gate B", "exit", capacity=gate_b_cap)
    v.add_route("A", "Corridor", capacity=corridor_cap, length=5).add_route("Corridor", "Gate A", capacity=10_000, length=5)
    v.add_route("B", "Gate B", capacity=10_000, length=5)
    v.add_group("ga", "A", size_a).add_group("gb", "B", size_b)
    p = RoutingProblem(v, paths_per_group=1)
    return p.evaluate([1, 1])


def test_people_over_capacity_counts_the_same_people_once():
    # 780 people through a 500 corridor to a 500 gate: the same 280 people are too many twice.
    ev = _two_exit_venue(780, 10, gate_a_cap=500, gate_b_cap=100, corridor_cap=500)
    assert ev.people_over_capacity == 280
    assert ev.total_excess == 560


def test_people_over_capacity_adds_separate_overloads():
    # 280 too many at Gate A and, separately, 50 too many at Gate B: different people.
    ev = _two_exit_venue(780, 150, gate_a_cap=500, gate_b_cap=100, corridor_cap=10_000)
    assert ev.people_over_capacity == 330
    assert ev.capacity_violations == 2


def test_people_over_capacity_is_zero_when_everything_fits():
    assert _two_exit_venue(100, 50, 500, 100, 500).people_over_capacity == 0
