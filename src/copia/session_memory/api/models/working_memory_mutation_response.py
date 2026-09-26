from pydantic import Field

from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem


class WorkingMemoryMutationResponse(WorkingMemoryItem):
    memory_events: list[MemoryEvent] = Field(default_factory=list)
