from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from copia.scheduled_jobs.data.atomic_json_write import atomic_json_write
from copia.scheduled_jobs.domain.models.scheduled_run import ScheduledRun
from copia.security.domain.services.credential_sanitizer import sanitize_error, sanitize_text


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
