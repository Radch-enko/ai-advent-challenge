from collections.abc import Callable
from typing import Any

from copia.mcp.application.mcp_turn_worker_runtime import McpTurnWorkerRuntime
from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime
from copia.mcp.domain.services.mcp_tool_loop import McpToolLoop


class McpTurnWorker:
    def __init__(self, get_runtime: Callable[[], McpTurnWorkerRuntime]) -> None:
        self._get_runtime = get_runtime

    async def run(self, turn: McpTurnRuntime, request: Any) -> None:
        runtime = self._get_runtime()
        message_lock = runtime.message_lock(turn.session_id)
        await runtime.threadpool(message_lock.lock.acquire)
        background = runtime.background_factory()
        try:
            session = await runtime.get_session(turn.session_id)
            config = (
                request.config
                if request.config is not None and session.profile_name is None
                else session.config
            )
            tools = await runtime.resolve_tools(config)
            loop = McpToolLoop(
                runtime.router,
                tools,
                request_approval=lambda approval: runtime.turn_approval(turn, approval),
                execute=runtime.execute_tool,
                emit=lambda event_type, data: runtime.emit_turn(turn, event_type, data),
                audit=lambda entry: turn.audits.append(entry),
            )
            response = await runtime.send_locked(
                turn.session_id, request, background, completion=loop.complete
            )
            for audit in turn.audits:
                runtime.agent_logs.append_tool_call(response.agent_log_id, audit)
            with turn.lock:
                turn.result = response
                turn.status = "completed"
            await runtime.threadpool(
                runtime.persist_turn, turn.session_id, turn.id, "completed", None
            )
            runtime.emit_turn(turn, "final", response.model_dump(mode="json"))
            await background()
        except Exception as error:
            with turn.lock:
                turn.error = runtime.sanitize_error(str(error))[:1000]
                turn.status = "failed"
            await runtime.threadpool(
                runtime.persist_turn, turn.session_id, turn.id, "failed", turn.error
            )
            runtime.emit_turn(turn, "error", {"message": turn.error})
        finally:
            message_lock.lock.release()
            runtime.release_message_lock(message_lock)
            with runtime.turns_lock:
                runtime.workers.pop(turn.id, None)
