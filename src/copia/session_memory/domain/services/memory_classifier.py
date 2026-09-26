from typing import Protocol

from copia.session_memory.domain.models.memory_candidate import MemoryCandidate
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.domain.models.chat_message import ChatMessage


class MemoryClassifier(Protocol):
    def classify(
        self,
        message: str,
        transcript: list[ChatMessage],
        working_memory: list[WorkingMemoryItem],
        previous_assistant: str | None = None,
    ) -> list[MemoryCandidate]: ...
