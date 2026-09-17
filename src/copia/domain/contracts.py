from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models.agent_log import AgentLogExchange, AgentLogTurn
from .models.config import ChatMessage
from .models.memory import LongTermMemoryItem, WorkingMemoryItem


@runtime_checkable
class AgentLogSink(Protocol):
    """Minimal provider logging contract used by domain routing composition."""

    max_body_bytes: int

    def append(self, exchange: AgentLogExchange) -> bool: ...


@runtime_checkable
class AgentLogRepository(Protocol):
    """Durable storage contract for completed and in-progress agent turns."""

    def save(self, turn: AgentLogTurn) -> None: ...

    def load(self, session_id: str, agent_turn_id: str) -> AgentLogTurn | None: ...

    def delete(self, session_id: str, agent_turn_id: str) -> None: ...

    def delete_session(self, session_id: str) -> None: ...


@runtime_checkable
class ShortTermTranscriptStore(Protocol):
    """Provider-agnostic storage contract for a session transcript."""

    def load_transcript(self, session_id: str) -> list[ChatMessage]: ...

    def save_transcript(self, session_id: str, messages: list[ChatMessage]) -> None: ...


@runtime_checkable
class WorkingMemoryStore(Protocol):
    def load(self, session_id: str) -> list[WorkingMemoryItem]: ...

    def save(self, session_id: str, items: list[WorkingMemoryItem]) -> None: ...

    def save_automatic(
        self,
        session_id: str,
        before: list[WorkingMemoryItem],
        after: list[WorkingMemoryItem],
    ) -> None: ...


@runtime_checkable
class LongTermMemoryStore(Protocol):
    def load(self, profile_name: str) -> list[LongTermMemoryItem]: ...

    def save(self, profile_name: str, items: list[LongTermMemoryItem]) -> None: ...

    def create(self, profile_name: str, item: LongTermMemoryItem) -> LongTermMemoryItem: ...

    def update(
        self, profile_name: str, item_id: str, changes: dict[str, object]
    ) -> LongTermMemoryItem: ...

    def delete_item(self, profile_name: str, item_id: str) -> None: ...
