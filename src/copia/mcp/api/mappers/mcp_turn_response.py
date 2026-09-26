from copia.mcp.api.models.mcp_turn_response import McpTurnResponse
from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime


def make_mcp_turn_response(turn: McpTurnRuntime) -> McpTurnResponse:
    with turn.lock:
        return McpTurnResponse(
            id=turn.id,
            session_id=turn.session_id,
            status=turn.status,  # type: ignore[arg-type]
            approval=turn.approval,
            result=turn.result,
            error=turn.error,
        )
