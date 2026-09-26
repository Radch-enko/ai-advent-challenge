from collections.abc import Awaitable, Callable

from fastapi.concurrency import run_in_threadpool

from copia.agent_logs.api.models.agent_log_response import AgentLogResponse
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agent_logs.domain.models.agent_log_turn import AgentLogTurn
from copia.scheduled_jobs.api.load_run_log import load_run_log
from copia.scheduled_jobs.api.require_job import require_job
from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner
from copia.scheduled_jobs.data.scheduled_runs_repository import ScheduledRunsRepository


def make_get_latest_scheduled_run_log(
    get_runner: Callable[[], ScheduledRunner],
    get_runs: Callable[[], ScheduledRunsRepository],
    get_log_store: Callable[[], AgentLogStore],
    render_log: Callable[[AgentLogTurn], AgentLogResponse],
) -> Callable[[str], Awaitable[AgentLogResponse]]:
    async def get_latest_scheduled_run_log(job_id: str) -> AgentLogResponse:
        require_job(get_runner(), job_id)
        run = await run_in_threadpool(get_runs().latest, job_id)
        return await load_run_log(job_id, run, get_log_store, render_log)

    return get_latest_scheduled_run_log
