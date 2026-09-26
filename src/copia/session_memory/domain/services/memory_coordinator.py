import uuid
from collections.abc import Callable
from typing import Any

from copia.agents.domain.models.agent_config import AgentConfig
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.security.domain.services.credential_sanitizer import sanitize_error, sanitize_value
from copia.session_memory.domain.contracts.working_memory_store import WorkingMemoryStore
from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.session_memory.domain.services.hybrid_memory_policy import HybridMemoryPolicy
from copia.session_memory.domain.services.memory_classifier import MemoryClassifier
from copia.sessions.domain.models.chat_message import ChatMessage


class MemoryCoordinator:
    def __init__(
        self,
        classifier: MemoryClassifier,
        store: WorkingMemoryStore,
        session_id: str,
        config: AgentConfig,
    ) -> None:
        self._classifier = classifier
        self._store = store
        self._session_id = session_id
        self._config = config

    def classify_and_apply(
        self,
        content: str,
        history: list[ChatMessage],
        working_memory: list[WorkingMemoryItem],
        pending_memory: list[PendingMemorySuggestion],
        memory_events: list[MemoryEvent],
        on_applied: Callable[
            [
                list[WorkingMemoryItem],
                list[PendingMemorySuggestion],
                list[MemoryEvent],
                dict[str, Any],
            ],
            None,
        ],
    ) -> None:
        try:
            candidates = self._classifier.classify(
                content,
                history[-7:],
                working_memory,
                history[-2].content if len(history) > 1 else None,
            )
            classifier_error = getattr(self._classifier, "last_error", None)
            if classifier_error is not None:
                classifier_error = sanitize_error(str(classifier_error))
            memory_details = self._memory_details(content, working_memory, classifier_error)
            if memory_events and memory_events[-1].action == "saved":
                memory_events[-1] = memory_events[-1].model_copy(update=memory_details)
            if classifier_error is not None:
                memory_events.append(
                    MemoryEvent(
                        id=str(uuid.uuid4()),
                        scope="working",
                        action="error",
                        message=classifier_error,
                        **memory_details,
                    )
                )
                return
            # Проверяем все кандидаты до применения политики, чтобы ошибка не изменила память частично.
            candidates = [candidate.model_copy(deep=True) for candidate in candidates]
            updated_working, updated_pending, events = HybridMemoryPolicy().apply(
                self._session_id,
                candidates,
                self._store,
                pending_memory,
            )
            on_applied(
                updated_working,
                updated_pending,
                events,
                memory_details,
            )
        except Exception as error:
            self._record_failure(memory_events, error)

    def _memory_details(
        self,
        content: str,
        working_memory: list[WorkingMemoryItem],
        classifier_error: str | None,
    ) -> dict[str, Any]:
        memory_trace = getattr(self._classifier, "last_trace", None)
        if memory_trace is not None:
            memory_trace = ProviderTrace.model_validate(sanitize_value(memory_trace.model_dump()))
        memory_duration = getattr(self._classifier, "last_duration_seconds", None)
        if memory_trace is None and memory_duration is not None:
            memory_trace = ProviderTrace(
                status_code=0 if classifier_error is not None else 200,
                request_body=getattr(self._classifier, "last_request_body", None)
                or {
                    "operation": "memory_classification",
                    "message": content,
                    "working_memory": [item.model_dump(mode="json") for item in working_memory],
                },
                response_body={"error": classifier_error}
                if classifier_error is not None
                else {"status": "completed"},
            )
        return {
            "provider": self._config.provider.value,
            "model": self._config.model,
            "duration_seconds": memory_duration,
            "trace": memory_trace,
        }

    @staticmethod
    def _record_failure(memory_events: list[MemoryEvent], error: Exception) -> None:
        memory_events.append(
            MemoryEvent(
                id=str(uuid.uuid4()),
                scope="working",
                action="error",
                message=sanitize_error(
                    "Memory update failed: "
                    f"{type(error).__name__}: {str(error) or type(error).__name__}"
                ),
            )
        )
