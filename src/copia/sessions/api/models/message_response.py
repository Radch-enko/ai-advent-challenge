from __future__ import annotations

from pydantic import BaseModel, Field

from copia.providers.domain.models.llm_response import LLMResponse
from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.domain.models.facts_update_event import FactsUpdateEvent
from copia.sessions.domain.models.summarization_event import SummarizationEvent


class MessageResponse(BaseModel):
    response: LLMResponse
    summarization_events: list[SummarizationEvent] = Field(default_factory=list)
    facts_events: list[FactsUpdateEvent] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)
    memory_events: list[MemoryEvent] = Field(default_factory=list)
    pending_memory: list[PendingMemorySuggestion] = Field(default_factory=list)
    working_memory: list[WorkingMemoryItem] = Field(default_factory=list)
