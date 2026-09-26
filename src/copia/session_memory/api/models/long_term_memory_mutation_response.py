from pydantic import Field

from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.session_memory.domain.models.memory_event import MemoryEvent


class LongTermMemoryMutationResponse(LongTermMemoryItem):
    memory_events: list[MemoryEvent] = Field(default_factory=list)
