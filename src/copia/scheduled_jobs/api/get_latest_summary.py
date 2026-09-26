from collections.abc import Awaitable, Callable

from fastapi.concurrency import run_in_threadpool

from copia.scheduled_jobs.api.models.scheduled_summary_response import ScheduledSummaryResponse
from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner
from copia.scheduled_jobs.data.scheduled_runs_repository import ScheduledRunsRepository


def make_get_latest_scheduled_summary(
    get_runner: Callable[[], ScheduledRunner],
    get_runs: Callable[[], ScheduledRunsRepository],
) -> Callable[[], Awaitable[ScheduledSummaryResponse]]:
    async def get_latest_scheduled_summary() -> ScheduledSummaryResponse:
        summary_jobs = [job for job in get_runner().jobs.values() if job.kind == "expense_summary"]
        if not summary_jobs:
            return ScheduledSummaryResponse(job_id=None, latest_run=None, published_run=None)
        latest_runs = [await run_in_threadpool(get_runs().latest, job.id) for job in summary_jobs]
        published_runs = [
            await run_in_threadpool(get_runs().latest_completed, job.id) for job in summary_jobs
        ]
        latest = max(
            (run for run in latest_runs if run), key=lambda run: run.scheduled_at, default=None
        )
        published = max(
            (run for run in published_runs if run), key=lambda run: run.scheduled_at, default=None
        )
        return ScheduledSummaryResponse(
            job_id=published.job_id
            if published
            else latest.job_id
            if latest
            else summary_jobs[0].id,
            latest_run=latest,
            published_run=published,
        )

    return get_latest_scheduled_summary
