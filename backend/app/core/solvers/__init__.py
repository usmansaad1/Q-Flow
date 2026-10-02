from app.core.solvers.base import SolverResult
from app.core.solvers.naive import solve_naive
from app.core.solvers.exact import solve_exact
from app.core.solvers.cpsat import solve_cpsat
from app.core.solvers.quantum import QAOAConfig, solve_qaoa_ideal, solve_qaoa_noisy

CLASSICAL_SOLVERS = {
    "naive": solve_naive,
    "classical_exact": solve_exact,
    "classical_cpsat": solve_cpsat,
}

QUANTUM_SOLVERS = {
    "qaoa_ideal": solve_qaoa_ideal,
    "qaoa_noisy": solve_qaoa_noisy,
}

__all__ = ["SolverResult", "QAOAConfig", "solve_naive", "solve_exact", "solve_cpsat",
           "solve_qaoa_ideal", "solve_qaoa_noisy", "CLASSICAL_SOLVERS", "QUANTUM_SOLVERS"]
