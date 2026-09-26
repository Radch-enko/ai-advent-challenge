from collections.abc import Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.agent_logs.api.models.agent_log_response import AgentLogResponse
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agent_logs.domain.models.agent_log_turn import AgentLogTurn
from copia.scheduled_jobs.domain.models.scheduled_run import ScheduledRun


async def load_run_log(
    job_id: str,
    run: ScheduledRun | None,
    get_log_store: Callable[[], AgentLogStore],
    render_log: Callable[[AgentLogTurn], AgentLogResponse],
) -> AgentLogResponse:
    if run is None or run.agent_log_id is None:
        raise HTTPException(404, detail="Scheduled agent log is unavailable")
    turn = await run_in_threadpool(
        get_log_store().get_turn, f"scheduled-{job_id}", run.agent_log_id
    )
    if turn is None:
        raise HTTPException(404, detail="Scheduled agent log is unavailable")
    return render_log(turn)
