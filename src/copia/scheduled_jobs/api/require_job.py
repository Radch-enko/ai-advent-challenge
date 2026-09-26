from fastapi import HTTPException

from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner


def require_job(runner: ScheduledRunner, job_id: str) -> None:
    if job_id not in runner.jobs:
        raise HTTPException(404, detail="Scheduled job is unavailable")
