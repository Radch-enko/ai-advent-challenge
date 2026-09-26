from collections.abc import Callable

from fastapi import APIRouter

from copia.agent_logs.api.models.agent_log_response import AgentLogResponse
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agent_logs.domain.models.agent_log_turn import AgentLogTurn
from copia.scheduled_jobs.api.get_latest_run import make_get_latest_scheduled_run
from copia.scheduled_jobs.api.get_latest_run_log import make_get_latest_scheduled_run_log
from copia.scheduled_jobs.api.get_latest_summary import make_get_latest_scheduled_summary
from copia.scheduled_jobs.api.get_run_log import make_get_scheduled_run_log
from copia.scheduled_jobs.api.get_statuses import make_get_scheduled_job_statuses
from copia.scheduled_jobs.api.models.scheduled_job_status_response import ScheduledJobStatusResponse
from copia.scheduled_jobs.api.models.scheduled_summary_response import ScheduledSummaryResponse
from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner
from copia.scheduled_jobs.data.scheduled_runs_repository import ScheduledRunsRepository


def create_scheduled_jobs_router(
    get_runner: Callable[[], ScheduledRunner],
    get_runs: Callable[[], ScheduledRunsRepository],
    get_log_store: Callable[[], AgentLogStore],
    render_log: Callable[[AgentLogTurn], AgentLogResponse],
) -> APIRouter:
    router = APIRouter()
    router.add_api_route(
        "/scheduled-jobs/status",
        make_get_scheduled_job_statuses(get_runner),
        methods=["GET"],
        response_model=list[ScheduledJobStatusResponse],
    )
    router.add_api_route(
        "/scheduled-summaries/latest",
        make_get_latest_scheduled_summary(get_runner, get_runs),
        methods=["GET"],
        response_model=ScheduledSummaryResponse,
    )
    router.add_api_route(
        "/scheduled-jobs/{job_id}/runs/latest",
        make_get_latest_scheduled_run(get_runner, get_runs),
        methods=["GET"],
        response_model=ScheduledSummaryResponse,
    )
    router.add_api_route(
        "/scheduled-jobs/{job_id}/runs/latest/log",
        make_get_latest_scheduled_run_log(get_runner, get_runs, get_log_store, render_log),
        methods=["GET"],
        response_model=AgentLogResponse,
    )
    router.add_api_route(
        "/scheduled-jobs/{job_id}/runs/{scheduled_at}/log",
        make_get_scheduled_run_log(get_runner, get_runs, get_log_store, render_log),
        methods=["GET"],
        response_model=AgentLogResponse,
    )
    return router
