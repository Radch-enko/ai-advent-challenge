from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.security.domain.services.credential_sanitizer import sanitize_error, sanitize_value
from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.sessions.domain.models.facts_update_event import FactsUpdateEvent
from copia.sessions.domain.models.summarization_event import SummarizationEvent


def safe_trace(trace: ProviderTrace | None) -> ProviderTrace | None:
    if trace is None:
        return None
    return ProviderTrace(
        status_code=trace.status_code,
        request_body=sanitize_value(trace.request_body),
        response_body=sanitize_value(trace.response_body),
    )


def safe_error_text(value: str | None) -> str | None:
    if value is None:
        return None
    return sanitize_error(value)


def safe_summarization_events(events: list[SummarizationEvent]) -> list[SummarizationEvent]:
    return [
        event.model_copy(
            deep=True,
            update={"trace": safe_trace(event.trace), "error": safe_error_text(event.error)},
        )
        for event in events
    ]


def safe_facts_events(events: list[FactsUpdateEvent]) -> list[FactsUpdateEvent]:
    return [
        event.model_copy(
            deep=True,
            update={"trace": safe_trace(event.trace), "error": safe_error_text(event.error)},
        )
        for event in events
    ]


def safe_memory_events(events: list[MemoryEvent]) -> list[MemoryEvent]:
    return [
        event.model_copy(
            deep=True,
            update={"trace": safe_trace(event.trace), "message": safe_error_text(event.message)},
        )
        for event in events
    ]


def session_failure_trace(error: ProviderError) -> ProviderTrace:
    return ProviderTrace(
        status_code=error.status_code,
        request_body=sanitize_value(error.request_body),
        response_body=sanitize_value(
            error.response_body
            if isinstance(error.response_body, dict)
            else {"raw": error.response_body}
        ),
    )
