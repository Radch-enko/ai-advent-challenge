from collections.abc import Callable
from typing import Any

from copia.conversations.application.conversation_run import ConversationRun
from copia.mcp.application.mcp_conversation_worker_runtime import McpConversationWorkerRuntime
from copia.mcp.domain.services.mcp_tool_loop import McpToolLoop


class McpConversationWorker:
    def __init__(self, get_runtime: Callable[[], McpConversationWorkerRuntime]) -> None:
        self._get_runtime = get_runtime

    async def run(
        self,
        conversation: ConversationRun,
        request: Any,
        emit: Callable[[str, dict[str, Any]], None],
    ) -> Any:
        runtime = self._get_runtime()
        if conversation.session_id is None:
            raise ValueError("MCP conversation requires a session target")
        session_id = conversation.session_id
        message_lock = runtime.message_lock(session_id)
        await runtime.threadpool(message_lock.lock.acquire)
        background = runtime.background_factory()
        emit_event = emit
        try:
            session = await runtime.get_session(session_id)
            config = (
                request.config
                if request.config is not None and session.profile_name is None
                else session.config
            )
            tools = await runtime.resolve_tools(config)
            loop = McpToolLoop(
                runtime.router,
                tools,
                request_approval=conversation.request_approval,
                execute=runtime.execute_tool,
                emit=emit_event,
                finalize=lambda response, artifacts: runtime.finalize_response(
                    session_id, response, artifacts
                ),
                publish_artifacts=lambda artifacts: runtime.publish_artifacts(
                    session_id, artifacts
                ),
                stream_completion=runtime.stream_completion,
            )
            response = await runtime.send_locked(
                session_id, request, background, completion=loop.complete
            )
            emit_event("final", response.model_dump(mode="json"))
            await background()
            return response
        except Exception as error:
            raise RuntimeError(runtime.sanitize_error(str(error))[:1000]) from error
        finally:
            message_lock.lock.release()
            runtime.release_message_lock(message_lock)
