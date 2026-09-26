from collections.abc import Awaitable, Callable

from fastapi.concurrency import run_in_threadpool

from copia.scheduled_jobs.api.models.scheduled_job_status_response import ScheduledJobStatusResponse
from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner


def make_get_scheduled_job_statuses(
    get_runner: Callable[[], ScheduledRunner],
) -> Callable[[], Awaitable[list[ScheduledJobStatusResponse]]]:
    async def get_scheduled_job_statuses() -> list[ScheduledJobStatusResponse]:
        values = await run_in_threadpool(get_runner().job_statuses)
        return [ScheduledJobStatusResponse.model_validate(value) for value in values]

    return get_scheduled_job_statuses
