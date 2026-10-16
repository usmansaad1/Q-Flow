# WHAT THIS FILE IS FOR: the front door of the "solvers" folder.
# A solver is a method that picks one exit route for every group of people.
# This file gathers all the solvers in one place so the rest of the app can find them by name.

from app.core.solvers.base import SolverResult
from app.core.solvers.naive import solve_naive
from app.core.solvers.exact import solve_exact
from app.core.solvers.cpsat import solve_cpsat
from app.core.solvers.quantum import QAOAConfig, solve_qaoa_ideal, solve_qaoa_noisy

# The ordinary computer methods, listed by the short name the app uses for each one.
# Simple shortest path, a full check of every plan, and Google's CP SAT planning engine.
CLASSICAL_SOLVERS = {
    "naive": solve_naive,
    "classical_exact": solve_exact,
    "classical_cpsat": solve_cpsat,
}

# The quantum methods, run on a simulated quantum computer.
# "ideal" is a perfect machine; "noisy" adds the errors real machines make.
QUANTUM_SOLVERS = {
    "qaoa_ideal": solve_qaoa_ideal,
    "qaoa_noisy": solve_qaoa_noisy,
}

# The list of names other files are allowed to import from this folder.
__all__ = ["SolverResult", "QAOAConfig", "solve_naive", "solve_exact", "solve_cpsat",
           "solve_qaoa_ideal", "solve_qaoa_noisy", "CLASSICAL_SOLVERS", "QUANTUM_SOLVERS"]
