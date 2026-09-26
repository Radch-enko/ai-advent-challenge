from __future__ import annotations

from typing import Protocol, runtime_checkable

from copia.sessions.domain.models.chat_message import ChatMessage


@runtime_checkable
class ShortTermTranscriptStore(Protocol):
    """Provider-agnostic storage contract for a session transcript."""

    def load_transcript(self, session_id: str) -> list[ChatMessage]: ...

    def save_transcript(self, session_id: str, messages: list[ChatMessage]) -> None: ...
