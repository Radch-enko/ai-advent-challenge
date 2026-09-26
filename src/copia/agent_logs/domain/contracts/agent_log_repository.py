from __future__ import annotations

from typing import Protocol, runtime_checkable

from copia.agent_logs.domain.models.agent_log_turn import AgentLogTurn


@runtime_checkable
class AgentLogRepository(Protocol):
    """Durable storage contract for completed and in-progress agent turns."""

    def save(self, turn: AgentLogTurn) -> None: ...

    def load(self, session_id: str, agent_turn_id: str) -> AgentLogTurn | None: ...

    def delete(self, session_id: str, agent_turn_id: str) -> None: ...

    def delete_session(self, session_id: str) -> None: ...
