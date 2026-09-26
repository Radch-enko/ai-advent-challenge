from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime
from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.sessions.data.sessions_repository import SessionsRepository


class McpTurnState:
    def __init__(
        self,
        get_sessions: Callable[[], SessionsRepository],
        get_lifecycle_lock: Callable[[], Any],
    ) -> None:
        self._get_sessions = get_sessions
        self._get_lifecycle_lock = get_lifecycle_lock

    def emit(self, turn: McpTurnRuntime, event_type: str, data: dict[str, Any]) -> None:
        with turn.lock:
            turn.events.append({"id": len(turn.events) + 1, "type": event_type, "data": data})

    def persist(
        self, session_id: str, turn_id: str, status_value: str, error: str | None = None
    ) -> None:
        with self._get_lifecycle_lock():
            sessions = self._get_sessions()
            session = sessions.load(session_id)
            if session is None:
                return
            session.mcp_turn_id = turn_id
            session.mcp_turn_status = status_value  # type: ignore[assignment]
            session.mcp_turn_error = error
            session.updated_at = datetime.now(UTC)
            sessions.save(session)

    def request_approval(
        self,
        turn: McpTurnRuntime,
        approval: McpApproval,
        persist: Callable[..., None],
    ) -> bool:
        with turn.lock:
            turn.approval = approval
            turn.status = "waiting_for_approval"
            turn.decision = None
            turn.decision_event.clear()
        persist(turn.session_id, turn.id, "waiting_for_approval")
        turn.decision_event.wait()
        with turn.lock:
            decision = bool(turn.decision)
            turn.approval = None
            turn.status = "running"
        persist(turn.session_id, turn.id, "running")
        return decision
