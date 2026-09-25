from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..data.scheduled_runs_repository import ScheduledRunsRepository, atomic_json_write
from ..domain.models.scheduled_job import ScheduledJob, ScheduledJobsConfig, ScheduledRun
from ..domain.services.credential_sanitizer import sanitize_error

logger = logging.getLogger(__name__)
JobHandler = Callable[[ScheduledJob, datetime, datetime], tuple[str, str]]


class ScheduledJobFailure(RuntimeError):
    def __init__(self, message: str, agent_log_id: str | None = None) -> None:
        super().__init__(message)
        self.agent_log_id = agent_log_id


def trigger_for(job: ScheduledJob, activated_at: datetime):
    spec = job.schedule
    if spec.type == "interval":
        assert spec.minutes is not None
        return IntervalTrigger(
            minutes=spec.minutes,
            start_date=activated_at + timedelta(minutes=spec.minutes),
            timezone=UTC,
        )
    assert spec.time is not None and spec.timezone is not None
    hour, minute = map(int, spec.time.split(":"))
    return CronTrigger(
        hour=hour,
        minute=minute,
        day_of_week=spec.day_of_week,
        timezone=ZoneInfo(spec.timezone),
    )


def previous_fire(job: ScheduledJob, activated_at: datetime, at: datetime) -> datetime | None:
    if job.schedule.type == "interval":
        assert job.schedule.minutes is not None
        delta = timedelta(minutes=job.schedule.minutes)
        count = (at - activated_at) // delta
        return activated_at + count * delta if count >= 1 else None
    lookback = timedelta(days=8 if job.schedule.day_of_week else 2)
    trigger = trigger_for(job, activated_at)
    cursor = at - lookback
    latest = None
    while True:
        next_fire = trigger.get_next_fire_time(latest, cursor)
        if next_fire is None or next_fire.astimezone(UTC) > at:
            value = latest.astimezone(UTC) if latest else None
            return value if value is not None and value > activated_at else None
        latest = next_fire
        cursor = next_fire


def preceding_fire(job: ScheduledJob, activated_at: datetime, current: datetime) -> datetime:
    if job.schedule.type == "interval":
        assert job.schedule.minutes is not None
        return current - timedelta(minutes=job.schedule.minutes)
    previous = previous_fire(job, current - timedelta(days=16), current - timedelta(microseconds=1))
    if previous is None:
        raise ValueError("Could not calculate previous calendar fire time")
    return previous


def report_window(
    job: ScheduledJob, activated_at: datetime, scheduled_at: datetime, execution_at: datetime
) -> tuple[datetime, datetime]:
    if job.report_period.type == "scheduled_interval":
        return preceding_fire(job, activated_at, scheduled_at), scheduled_at
    assert job.report_period.timezone is not None
    local_now = execution_at.astimezone(ZoneInfo(job.report_period.timezone))
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    end = max(execution_at.astimezone(UTC), start + timedelta(microseconds=1))
    return start, end


class ScheduledRunner:
    def __init__(
        self,
        config_path: Path,
        state_path: Path,
        runs: ScheduledRunsRepository,
        handlers: dict[str, JobHandler],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.config_path = config_path.expanduser()
        self.state_path = state_path.expanduser()
        self.runs = runs
        self.handlers = handlers
        self.now = now
        self.scheduler = BackgroundScheduler(timezone=UTC)
        self.jobs: dict[str, ScheduledJob] = {}
        self.catchup_job_ids: dict[str, str] = {}
        self.state: dict[str, dict[str, str]] = {}
        self.lock = threading.RLock()

    def start(self) -> None:
        if self.config_path.exists():
            config = ScheduledJobsConfig.model_validate_json(
                self.config_path.read_text(encoding="utf-8")
            )
        else:
            config = ScheduledJobsConfig()
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        new_jobs: set[str] = set()
        for job in config.jobs:
            if not job.enabled:
                continue
            if job.kind not in self.handlers:
                raise ValueError(f"Unknown scheduled job kind: {job.kind}")
            self.jobs[job.id] = job
            self.runs.fail_interrupted(job.id)
            fingerprint_data = job.model_dump(mode="json", exclude={"name"})
            if job.report_period.type == "scheduled_interval":
                fingerprint_data.pop("report_period")
            fingerprint = json.dumps(fingerprint_data, sort_keys=True)
            existing = self.state.get(job.id)
            if existing is None or existing.get("fingerprint") != fingerprint:
                new_jobs.add(job.id)
                self.state[job.id] = {
                    "fingerprint": fingerprint,
                    "activated_at": self.now().astimezone(UTC).isoformat(),
                }
            activated = datetime.fromisoformat(self.state[job.id]["activated_at"])
            last_processed = self.state[job.id].get("last_processed_at")
            if last_processed is not None:
                scheduled_at = datetime.fromisoformat(last_processed)
                if self.runs.get(job.id, scheduled_at) is None:
                    period_from, period_to = report_window(
                        job, activated, scheduled_at, scheduled_at
                    )
                    self.runs.save(
                        ScheduledRun(
                            job_id=job.id,
                            kind=job.kind,
                            scheduled_at=scheduled_at,
                            period_from=period_from,
                            period_to=period_to,
                            status="failed",
                            error="Backend stopped before the run was recorded",
                            started_at=scheduled_at,
                            finished_at=self.now(),
                        )
                    )
            self.scheduler.add_job(
                self.run_due,
                trigger_for(job, activated),
                args=(job.id,),
                id=job.id,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=None,
            )
        self._save_state()
        self.scheduler.start()
        for job_id in self.jobs:
            if job_id not in new_jobs:
                catchup_id = f"catchup-{job_id}"
                self.catchup_job_ids[job_id] = catchup_id
                self.scheduler.add_job(
                    self.run_due,
                    "date",
                    run_date=datetime.now(UTC) + timedelta(seconds=1),
                    args=(job_id,),
                    id=catchup_id,
                )

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    def _save_state(self) -> None:
        atomic_json_write(self.state_path, self.state)

    def job_statuses(self) -> list[dict[str, object]]:
        with self.lock:
            jobs = list(self.jobs.values())
        statuses: list[dict[str, object]] = []
        for job in jobs:
            scheduled = self.scheduler.get_job(job.id)
            catchup_id = self.catchup_job_ids.get(job.id)
            catchup = self.scheduler.get_job(catchup_id) if catchup_id else None
            next_runs = [
                item.next_run_time
                for item in (scheduled, catchup)
                if item is not None and item.next_run_time is not None
            ]
            latest = self.runs.latest(job.id)
            activated_at = datetime.fromisoformat(self.state[job.id]["activated_at"])
            current_run = (
                latest if latest is not None and latest.scheduled_at > activated_at else None
            )
            if current_run is not None and current_run.status == "running":
                state = "progress"
            elif current_run is not None and current_run.status == "completed":
                state = "completed"
            else:
                state = "wait"
            statuses.append(
                {
                    "id": job.id,
                    "name": job.name or job.id,
                    "status": state,
                    "next_run_at": min(next_runs) if next_runs else None,
                }
            )
        return statuses

    def run_due(self, job_id: str) -> ScheduledRun | None:
        with self.lock:
            job = self.jobs[job_id]
            state = self.state[job_id]
            activated = datetime.fromisoformat(state["activated_at"])
            execution_at = self.now().astimezone(UTC)
            scheduled_at = previous_fire(job, activated, execution_at)
            if scheduled_at is None:
                return None
            last = state.get("last_processed_at")
            if last is not None and scheduled_at <= datetime.fromisoformat(last):
                return None
            period_from, period_to = report_window(job, activated, scheduled_at, execution_at)
            state["last_processed_at"] = scheduled_at.isoformat()
            self._save_state()
            run = ScheduledRun(
                job_id=job.id,
                kind=job.kind,
                scheduled_at=scheduled_at,
                period_from=period_from,
                period_to=period_to,
                status="running",
                started_at=self.now(),
            )
            self.runs.save(run)
        try:
            answer, agent_log_id = self.handlers[job.kind](job, period_from, period_to)
            run = run.model_copy(
                update={"status": "completed", "answer": answer, "agent_log_id": agent_log_id}
            )
        except Exception as error:
            logger.exception("Scheduled job %s failed", job.id)
            run = run.model_copy(
                update={
                    "status": "failed",
                    "error": sanitize_error(str(error))[:1000],
                    "agent_log_id": getattr(error, "agent_log_id", None),
                }
            )
        run = run.model_copy(update={"finished_at": self.now()})
        self.runs.save(run)
        return run
