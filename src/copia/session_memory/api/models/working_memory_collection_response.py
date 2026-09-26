from pydantic import BaseModel, Field

from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem


class WorkingMemoryCollectionResponse(BaseModel):
    working_memory: list[WorkingMemoryItem] = Field(default_factory=list)
    memory_events: list[MemoryEvent] = Field(default_factory=list)
