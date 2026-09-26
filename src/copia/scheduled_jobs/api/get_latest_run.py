from collections.abc import Awaitable, Callable

from fastapi.concurrency import run_in_threadpool

from copia.scheduled_jobs.api.models.scheduled_summary_response import ScheduledSummaryResponse
from copia.scheduled_jobs.api.require_job import require_job
from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner
from copia.scheduled_jobs.data.scheduled_runs_repository import ScheduledRunsRepository


def make_get_latest_scheduled_run(
    get_runner: Callable[[], ScheduledRunner],
    get_runs: Callable[[], ScheduledRunsRepository],
) -> Callable[[str], Awaitable[ScheduledSummaryResponse]]:
    async def get_latest_scheduled_run(job_id: str) -> ScheduledSummaryResponse:
        require_job(get_runner(), job_id)
        return ScheduledSummaryResponse(
            job_id=job_id,
            latest_run=await run_in_threadpool(get_runs().latest, job_id),
            published_run=await run_in_threadpool(get_runs().latest_completed, job_id),
        )

    return get_latest_scheduled_run
