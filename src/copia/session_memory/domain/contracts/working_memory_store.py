from __future__ import annotations

from typing import Protocol, runtime_checkable

from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem


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
