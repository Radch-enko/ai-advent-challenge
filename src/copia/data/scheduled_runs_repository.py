from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ..domain.models.scheduled_job import ScheduledRun
from ..domain.services.credential_sanitizer import sanitize_error, sanitize_text


def atomic_json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


class ScheduledRunsRepository:
    def __init__(self, root: Path, retention: int = 50) -> None:
        self.root = root.expanduser()
        self.retention = retention

    def _path(self, job_id: str, scheduled_at: datetime) -> Path:
        slot = scheduled_at.astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
        return self.root / job_id / f"{slot}.json"

    def save(self, run: ScheduledRun) -> None:
        if run.error:
            run = run.model_copy(update={"error": sanitize_error(run.error)[:1000]})
        if run.answer:
            run = run.model_copy(update={"answer": sanitize_text(run.answer)})
        atomic_json_write(self._path(run.job_id, run.scheduled_at), run.model_dump(mode="json"))
        paths = sorted((self.root / run.job_id).glob("*.json"))
        for path in paths[: -self.retention]:
            path.unlink()

    def latest(self, job_id: str) -> ScheduledRun | None:
        paths = sorted((self.root / job_id).glob("*.json"))
        if not paths:
            return None
        return ScheduledRun.model_validate_json(paths[-1].read_text(encoding="utf-8"))

    def get(self, job_id: str, scheduled_at: datetime) -> ScheduledRun | None:
        path = self._path(job_id, scheduled_at)
        if not path.exists():
            return None
        return ScheduledRun.model_validate_json(path.read_text(encoding="utf-8"))

    def latest_completed(self, job_id: str) -> ScheduledRun | None:
        for path in reversed(sorted((self.root / job_id).glob("*.json"))):
            run = ScheduledRun.model_validate_json(path.read_text(encoding="utf-8"))
            if run.status == "completed":
                return run
        return None

    def fail_interrupted(self, job_id: str) -> None:
        for path in (self.root / job_id).glob("*.json"):
            run = ScheduledRun.model_validate_json(path.read_text(encoding="utf-8"))
            if run.status == "running":
                self.save(
                    run.model_copy(
                        update={
                            "status": "failed",
                            "error": "Backend stopped during this run",
                            "finished_at": datetime.now(UTC),
                        }
                    )
                )
