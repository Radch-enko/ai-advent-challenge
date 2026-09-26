from pydantic import BaseModel, Field

from copia.sessions.domain.models.facts_update_event import FactsUpdateEvent
from copia.sessions.domain.models.summarization_event import SummarizationEvent


class ConversationContext(BaseModel):
    summary: str = ""
    summarized_message_count: int = Field(default=0, ge=0)
    events: list[SummarizationEvent] = Field(default_factory=list)
    facts_events: list[FactsUpdateEvent] = Field(default_factory=list)
