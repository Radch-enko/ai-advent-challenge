from collections.abc import Callable

from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem


class SessionMemoryAccess:
    def __init__(
        self,
        get_working_repository: Callable[[], WorkingMemoryRepository],
        get_pending_repository: Callable[[], PendingMemoryRepository],
    ) -> None:
        self._get_working_repository = get_working_repository
        self._get_pending_repository = get_pending_repository

    def load_working(self, session_id: str) -> list[WorkingMemoryItem]:
        return self._get_working_repository().load(session_id)

    def load_pending(self, session_id: str) -> list[PendingMemorySuggestion]:
        return self._get_pending_repository().load(session_id)

    def save(
        self,
        session_id: str,
        working_items: list[WorkingMemoryItem],
        pending_items: list[PendingMemorySuggestion],
    ) -> None:
        self._get_working_repository().save_preserving_undo(session_id, working_items)
        self._get_pending_repository().save(session_id, pending_items)
