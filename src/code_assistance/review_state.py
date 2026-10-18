"""Durable local webhook and review job state."""

import os
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReviewJob:
    installation_id: int
    repository_id: int
    repository: str
    number: int
    head_sha: str
    base_sha: str

    @property
    def key(self) -> str:
        return f"{self.repository_id}:{self.number}:{self.head_sha}:{self.base_sha}"


class ReviewJobStore:
    def __init__(self, path: Path, *, recover_interrupted: bool = True) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            path.parent.chmod(0o700)
        self.path = path
        self._lock = threading.Lock()
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    job_key TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_key TEXT PRIMARY KEY,
                    installation_id INTEGER NOT NULL,
                    repository_id INTEGER NOT NULL,
                    repository TEXT NOT NULL,
                    number INTEGER NOT NULL,
                    head_sha TEXT NOT NULL,
                    base_sha TEXT NOT NULL,
                    state TEXT NOT NULL,
                    review_id INTEGER,
                    error TEXT
                );
                """
            )
            if recover_interrupted:
                with connection:
                    connection.execute("UPDATE jobs SET state = 'queued' WHERE state = 'running'")
        if os.name != "nt":
            path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=15)

    def enqueue(self, delivery_id: str, job: ReviewJob) -> bool:
        with self._lock, closing(self._connect()) as connection:
            with connection:
                return self._enqueue(connection, delivery_id, job)

    def _enqueue(self, connection: sqlite3.Connection, delivery_id: str, job: ReviewJob) -> bool:
        old_delivery = connection.execute(
            "SELECT job_key FROM deliveries WHERE delivery_id = ?", (delivery_id,)
        ).fetchone()
        if old_delivery is not None and old_delivery[0] != job.key:
            return False
        connection.execute(
            "INSERT OR IGNORE INTO deliveries(delivery_id, job_key) VALUES (?, ?)",
            (delivery_id, job.key),
        )
        connection.execute(
            """INSERT OR IGNORE INTO jobs(
                    job_key, installation_id, repository_id, repository, number,
                    head_sha, base_sha, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')""",
            (
                job.key,
                job.installation_id,
                job.repository_id,
                job.repository,
                job.number,
                job.head_sha,
                job.base_sha,
            ),
        )
        connection.execute(
            """UPDATE jobs SET state = 'queued', error = NULL
                   WHERE job_key = ? AND state IN ('failed', 'stale')""",
            (job.key,),
        )
        state = connection.execute(
            "SELECT state FROM jobs WHERE job_key = ?", (job.key,)
        ).fetchone()
        return state is not None and state[0] == "queued"

    def claim(self) -> ReviewJob | None:
        with self._lock, closing(self._connect()) as connection:
            with connection:
                return self._claim(connection)

    def _claim(self, connection: sqlite3.Connection) -> ReviewJob | None:
        row = connection.execute(
            """SELECT job_key, installation_id, repository_id, repository,
                    number, head_sha, base_sha FROM jobs WHERE state = 'queued'
                    ORDER BY rowid LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        connection.execute("UPDATE jobs SET state = 'running' WHERE job_key = ?", (row[0],))
        return ReviewJob(*row[1:])

    def finish(self, job: ReviewJob, state: str, review_id: int | None = None) -> None:
        if state not in {"done", "stale", "skipped"}:
            raise ValueError("Invalid review job state.")
        with self._lock, closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "UPDATE jobs SET state = ?, review_id = ?, error = NULL WHERE job_key = ?",
                    (state, review_id, job.key),
                )

    def fail(self, job: ReviewJob, error: str) -> None:
        with self._lock, closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "UPDATE jobs SET state = 'failed', error = ? WHERE job_key = ?",
                    (error[:500], job.key),
                )

    def prepare_redelivery(
        self,
        repository: str,
        number: int,
        *,
        head_sha: str | None = None,
        base_sha: str | None = None,
    ) -> tuple[ReviewJob, str, int | None]:
        """Mark one matching task retryable while preserving webhook delivery IDs."""
        conditions = ["repository = ? COLLATE NOCASE", "number = ?"]
        parameters: list[str | int] = [repository, number]
        if head_sha is not None:
            conditions.append("head_sha = ?")
            parameters.append(head_sha)
        if base_sha is not None:
            conditions.append("base_sha = ?")
            parameters.append(base_sha)

        with self._lock, closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """SELECT installation_id, repository_id, repository, number,
                              head_sha, base_sha, state, review_id, job_key
                         FROM jobs WHERE """
                    + " AND ".join(conditions)
                    + " ORDER BY rowid DESC LIMIT 1",
                    parameters,
                ).fetchone()
                if row is None:
                    raise ValueError("No stored review task matches this repository and PR.")
                if row[6] == "running":
                    raise ValueError("The matching review task is running; wait for it to finish.")

                job = ReviewJob(*row[:6])
                previous_state = str(row[6])
                previous_review_id = int(row[7]) if row[7] is not None else None
                connection.execute(
                    """UPDATE jobs SET state = 'failed', review_id = NULL, error = NULL
                         WHERE job_key = ?""",
                    (row[8],),
                )
                return job, previous_state, previous_review_id
