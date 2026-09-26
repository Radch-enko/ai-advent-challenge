from __future__ import annotations

from typing import Protocol, runtime_checkable

from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem


@runtime_checkable
class LongTermMemoryStore(Protocol):
    def load(self, profile_name: str) -> list[LongTermMemoryItem]: ...

    def save(self, profile_name: str, items: list[LongTermMemoryItem]) -> None: ...

    def create(self, profile_name: str, item: LongTermMemoryItem) -> LongTermMemoryItem: ...

    def update(
        self, profile_name: str, item_id: str, changes: dict[str, object]
    ) -> LongTermMemoryItem: ...

    def delete_item(self, profile_name: str, item_id: str) -> None: ...
