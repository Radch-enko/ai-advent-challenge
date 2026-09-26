from collections.abc import Callable

from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.models.context_strategy_name import ContextStrategyName


class SessionLongTermMemoryAccess:
    def __init__(self, get_repository: Callable[[], ProfileMemoryRepository]) -> None:
        self._get_repository = get_repository

    def for_session(self, session: ChatSession, facts: dict[str, str]) -> list[LongTermMemoryItem]:
        if session.profile_name is None or not session.long_term_memory_enabled:
            return []
        items = self._get_repository().load(session.profile_name)
        if session.config.context_management.strategy == ContextStrategyName.STICKY_FACTS:
            return [item for item in items if item.key not in facts]
        return items
