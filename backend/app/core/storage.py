"""
SQLite storage for experiments and runs (standard library only).

Database location: backend/data/qflow.db, or the QFLOW_DB environment variable.
One `experiments` row per experiment, one `runs` row per solver execution, and one
`venues` row per venue saved from the Lab.
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
CREATE TABLE IF NOT EXISTS hardware_jobs (
    job_id      TEXT PRIMARY KEY,
    backend     TEXT NOT NULL,
    payload     TEXT NOT NULL,
    response    TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_name  TEXT NOT NULL,
    solver      TEXT NOT NULL,
    num_qubits  INTEGER,
    quality     REAL,
    data        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS venues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    data        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
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

    def mark_interrupted(self) -> int:
        """Experiments still marked running when the backend starts can never finish:
        the process that ran them has stopped. Mark them failed so they can be deleted."""
        with self._conn() as c:
            cur = c.execute("UPDATE experiments SET status = 'failed', error = ?, finished_at = ? "
                            "WHERE status = 'running'",
                            ("Interrupted: the backend stopped before this experiment finished. "
                             "The runs recorded so far are kept.", _now()))
            return cur.rowcount

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

    # ----------------------------------------------------------------- venues
    def save_venue(self, data: dict) -> int:
        now = _now()
        with self._conn() as c:
            cur = c.execute("INSERT INTO venues (name, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                            (data["name"], json.dumps(data), now, now))
            return int(cur.lastrowid)

    def update_venue(self, venue_id: int, data: dict) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE venues SET name = ?, data = ?, updated_at = ? WHERE id = ?",
                            (data["name"], json.dumps(data), _now(), venue_id))
            return cur.rowcount > 0

    def get_venue(self, venue_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM venues WHERE id = ?", (venue_id,)).fetchone()
        if not row:
            return None
        return {**json.loads(row["data"]), "id": row["id"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_venues(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM venues ORDER BY updated_at DESC, id DESC").fetchall()
        return [{**json.loads(r["data"]), "id": r["id"], "created_at": r["created_at"],
                 "updated_at": r["updated_at"]} for r in rows]

    def delete_venue(self, venue_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM venues WHERE id = ?", (venue_id,)).rowcount > 0

    # --------------------------------------------------------------- lab runs
    def save_lab_run(self, venue_name: str, solver: str, num_qubits: int, quality: float | None, data: dict) -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO lab_runs (venue_name, solver, num_qubits, quality, data, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (venue_name, solver, num_qubits, quality, json.dumps(data, default=float), _now()))
            return int(cur.lastrowid)

    def list_lab_runs(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id, venue_name, solver, num_qubits, quality, created_at FROM lab_runs "
                             "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_lab_run(self, run_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM lab_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return {**json.loads(row["data"]), "id": row["id"], "created_at": row["created_at"]}

    def delete_lab_run(self, run_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM lab_runs WHERE id = ?", (run_id,)).rowcount > 0

    # ------------------------------------------------------- IBM hardware jobs
    def save_hardware_job(self, job_id: str, backend: str, payload: dict) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO hardware_jobs (job_id, backend, payload, created_at) VALUES (?, ?, ?, ?)",
                      (job_id, backend, json.dumps(payload, default=float), _now()))

    def get_hardware_job(self, job_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM hardware_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        return {"job_id": row["job_id"], "backend": row["backend"],
                "payload": json.loads(row["payload"]),
                "response": json.loads(row["response"]) if row["response"] else None,
                "error": row["error"]}

    def update_hardware_job(self, job_id: str, response: dict | None = None, error: str | None = None) -> None:
        with self._conn() as c:
            if response is not None:
                c.execute("UPDATE hardware_jobs SET response = ? WHERE job_id = ?",
                          (json.dumps(response, default=float), job_id))
            if error is not None:
                c.execute("UPDATE hardware_jobs SET error = ? WHERE job_id = ?", (error, job_id))
