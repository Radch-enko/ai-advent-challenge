from copia.providers.domain.models.llm_response import LLMResponse
from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.api.message_sanitizer import (
    safe_facts_events,
    safe_memory_events,
    safe_summarization_events,
)
from copia.sessions.api.models.session_llm_response import SessionLLMResponse
from copia.sessions.api.models.session_message_response import SessionMessageResponse
from copia.sessions.domain.models.facts_update_event import FactsUpdateEvent
from copia.sessions.domain.models.summarization_event import SummarizationEvent


def make_session_message_response(
    response: LLMResponse,
    agent_log_id: str,
    *,
    summarization_events: list[SummarizationEvent] | None = None,
    facts_events: list[FactsUpdateEvent] | None = None,
    facts: dict[str, str] | None = None,
    memory_events: list[MemoryEvent] | None = None,
    pending_memory: list[PendingMemorySuggestion] | None = None,
    working_memory: list[WorkingMemoryItem] | None = None,
) -> SessionMessageResponse:
    return SessionMessageResponse(
        response=SessionLLMResponse.from_response(response),
        agent_log_id=agent_log_id,
        summarization_events=safe_summarization_events(summarization_events or []),
        facts_events=safe_facts_events(facts_events or []),
        facts=facts or {},
        memory_events=safe_memory_events(memory_events or []),
        pending_memory=pending_memory or [],
        working_memory=working_memory or [],
    )
