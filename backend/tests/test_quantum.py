"""QAOA correctness checks. Kept small so the suite stays fast."""
import warnings

import numpy as np
import pytest

warnings.filterwarnings("ignore")

from qiskit import transpile
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator

from app.core.presets import get_preset, PRESETS
from app.core.problem import RoutingProblem
from app.core.solvers.quantum import (
    qubo_to_ising, build_qaoa_circuit, counts_to_probs, solve_qaoa_ideal, solve_qaoa_noisy, interp,
)


@pytest.fixture(scope="module")
def micro():
    return RoutingProblem(get_preset("micro_hall"))


@pytest.mark.parametrize("pid", list(PRESETS))
def test_ising_matches_qubo(pid):
    p = RoutingProblem(get_preset(pid))
    h, J, const = qubo_to_ising(p)
    energies = p.all_energies()
    n = p.num_variables
    for k in range(0, 2 ** n, max(1, 2 ** n // 64)):
        z = 1 - 2 * ((k >> np.arange(n)) & 1)
        e = const + sum(h[i] * z[i] for i in h) + sum(c * z[i] * z[j] for (i, j), c in J.items())
        assert e == pytest.approx(energies[k], abs=1e-9)


def test_bit_order_statevector_vs_aer(micro):
    """Counts keys and statevector indices must address the same plan."""
    qc, params = build_qaoa_circuit(micro, 1, measure=False)
    theta = [0.7, 0.4]
    sv_probs = Statevector(qc.assign_parameters(dict(zip(params, theta)))).probabilities()
    mq, mp = build_qaoa_circuit(micro, 1, measure=True)
    compiled = transpile(mq.assign_parameters(dict(zip(mp, theta))), basis_gates=["rz", "sx", "x", "cx"])
    counts = AerSimulator(seed_simulator=1).run(compiled, shots=40_000).result().get_counts()
    assert np.abs(counts_to_probs(counts, micro.num_variables) - sv_probs).max() < 0.02


def test_ideal_qaoa_beats_random(micro):
    r = solve_qaoa_ideal(micro, reps=2, shots=2048)
    m = r.extra["metrics"]
    assert m["prob_optimal"] > 2 * m["random_baseline"]["prob_optimal"]
    assert m["prob_feasible"] > m["random_baseline"]["prob_feasible"]
    assert r.evaluation["feasible"]


def test_noise_degrades_quality(micro):
    clean = solve_qaoa_noisy(micro, reps=2, noise="depolarizing", noise_level=0, shots=4096)
    noisy = solve_qaoa_noisy(micro, reps=2, noise="depolarizing", noise_level=10, shots=4096)
    assert noisy.extra["metrics"]["mean_approx_ratio"] < clean.extra["metrics"]["mean_approx_ratio"]


def test_interp_preserves_shape():
    t = interp(np.array([0.5, 0.3]), 1)
    assert t.shape == (4,)
    t3 = interp(t, 2)
    assert t3.shape == (6,)


def test_api_quantum(micro):
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).post("/api/v1/optimize", json={
        "preset_id": "micro_hall", "solver": "qaoa_noisy",
        "quantum": {"reps": 1, "shots": 1024, "noise": "depolarizing", "noise_level": 2}})
    assert r.status_code == 200
    q = r.json()["quality"]
    assert 0 <= q["mean_approx_ratio"] <= 1 and "random_baseline" in q
