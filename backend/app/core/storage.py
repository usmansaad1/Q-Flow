"""
SQLite storage for experiments and runs (standard library only).

Database location: backend/data/qflow.db, or the QFLOW_DB environment variable.
One `experiments` row per experiment, one `runs` row per solver execution.
Headline metrics get their own columns for easy querying; the full metrics
dictionary is kept as JSON so nothing is lost.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB = BACKEND_DIR / "data" / "qflow.db"


def results_dir() -> Path:
    """Where CSV and chart exports go: backend/results, or QFLOW_RESULTS."""
    return Path(os.environ.get("QFLOW_RESULTS") or BACKEND_DIR / "results")

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,
    title         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'running',
    config        TEXT NOT NULL DEFAULT '{}',
    summary       TEXT,
    error         TEXT,
    created_at    TEXT NOT NULL,
    finished_at   TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id      INTEGER REFERENCES experiments(id) ON DELETE CASCADE,
    instance           TEXT NOT NULL,
    num_qubits         INTEGER NOT NULL,
    method             TEXT NOT NULL,
    solver             TEXT NOT NULL,
    noise_model        TEXT,
    noise_level        REAL,
    reps               INTEGER,
    shots              INTEGER,
    prob_optimal       REAL,
    prob_feasible      REAL,
    mean_approx_ratio  REAL,
    best_is_optimal    INTEGER,
    random_prob_optimal REAL,
    random_mean_ratio  REAL,
    energy             REAL,
    optimal_energy     REAL,
    two_qubit_gates    INTEGER,
    depth              INTEGER,
    runtime_s          REAL,
    details            TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_experiment ON runs(experiment_id);
"""

RUN_COLUMNS = [
    "experiment_id", "instance", "num_qubits", "method", "solver", "noise_model", "noise_level",
    "reps", "shots", "prob_optimal", "prob_feasible", "mean_approx_ratio", "best_is_optimal",
    "random_prob_optimal", "random_mean_ratio", "energy", "optimal_energy", "two_qubit_gates",
    "depth", "runtime_s", "details", "created_at",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get("QFLOW_DB") or DEFAULT_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------ experiments
    def create_experiment(self, kind: str, title: str, config: dict) -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO experiments (kind, title, config, created_at) VALUES (?, ?, ?, ?)",
                            (kind, title, json.dumps(config), _now()))
            return int(cur.lastrowid)

    def finish_experiment(self, exp_id: int, summary: dict | None = None, error: str | None = None) -> None:
        with self._conn() as c:
            c.execute("UPDATE experiments SET status = ?, summary = ?, error = ?, finished_at = ? WHERE id = ?",
                      ("failed" if error else "done", json.dumps(summary) if summary else None,
                       error, _now(), exp_id))

    def list_experiments(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""SELECT e.*, COUNT(r.id) AS num_runs FROM experiments e
                                LEFT JOIN runs r ON r.experiment_id = e.id
                                GROUP BY e.id ORDER BY e.id DESC""").fetchall()
        return [self._exp_dict(r) for r in rows]

    def get_experiment(self, exp_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT e.*, (SELECT COUNT(*) FROM runs WHERE experiment_id = e.id) AS num_runs "
                            "FROM experiments e WHERE id = ?", (exp_id,)).fetchone()
        return self._exp_dict(row) if row else None

    def delete_experiment(self, exp_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM experiments WHERE id = ?", (exp_id,))

    @staticmethod
    def _exp_dict(row) -> dict:
        d = dict(row)
        d["config"] = json.loads(d["config"] or "{}")
        d["summary"] = json.loads(d["summary"]) if d.get("summary") else None
        return d

    # ------------------------------------------------------------------- runs
    def add_run(self, record: dict) -> int:
        record = {**record, "created_at": _now()}
        record["details"] = json.dumps(record.get("details") or {})
        values = [record.get(col) for col in RUN_COLUMNS]
        with self._conn() as c:
            cur = c.execute(f"INSERT INTO runs ({', '.join(RUN_COLUMNS)}) VALUES ({', '.join('?' * len(RUN_COLUMNS))})",
                            values)
            return int(cur.lastrowid)

    def get_runs(self, exp_id: int, include_details: bool = False) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM runs WHERE experiment_id = ? ORDER BY id", (exp_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if include_details:
                d["details"] = json.loads(d["details"] or "{}")
            else:
                d.pop("details", None)
            out.append(d)
        return out
