from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from copia.agent_logs.domain.services.agent_log_context import agent_log_operation
from copia.agents.domain.models.agent_config import AgentConfig
from copia.common.domain.services.runtime_context import with_current_datetime_context
from copia.invariants.domain.models.invariant import Invariant
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.providers.application.llm_router import LLMRouter, ProviderError
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.security.domain.services.credential_sanitizer import sanitize_error, sanitize_value
from copia.session_memory.domain.contracts.working_memory_store import WorkingMemoryStore
from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.session_memory.domain.services.memory_classifier import MemoryClassifier
from copia.session_memory.domain.services.memory_coordinator import MemoryCoordinator
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.context_strategy_name import ContextStrategyName
from copia.sessions.domain.models.conversation_context import ConversationContext
from copia.sessions.domain.models.facts_update_event import FactsUpdateEvent
from copia.sessions.domain.models.summarization_event import SummarizationEvent
from copia.sessions.domain.services.context_strategy import FactsUpdateFailed as FactsUpdateFailed
from copia.sessions.domain.services.context_strategy import (
    context_strategy_for,
    render_invariants_context,
)
from copia.user_profiles.domain.models.user_profile import UserProfile


class ProfilesSource(Protocol):
    def load(self) -> dict[str, AgentConfig]: ...


class SummarizationFailed(RuntimeError):
    def __init__(self, event: SummarizationEvent) -> None:
        super().__init__(event.error or "Conversation summarization failed")
        self.event = event


class SummarizationRetryRequired(RuntimeError):
    pass


class Agent:
    """A stateful conversation with a full transcript and compressed LLM context."""

    def __init__(
        self,
        config: AgentConfig,
        router: LLMRouter,
        history: list[ChatMessage] | None = None,
        context: ConversationContext | None = None,
        facts: dict[str, str] | None = None,
        long_term_memory: list[LongTermMemoryItem] | None = None,
        long_term_memory_loader: Callable[[], list[LongTermMemoryItem]] | None = None,
        context_window: int | None = None,
        working_memory: list[WorkingMemoryItem] | None = None,
        working_memory_store: WorkingMemoryStore | None = None,
        session_id: str | None = None,
        memory_classifier: MemoryClassifier | None = None,
        pending_memory: list[PendingMemorySuggestion] | None = None,
        user_profile: UserProfile | None = None,
        invariants: list[Invariant] | None = None,
    ) -> None:
        self.config = config
        self._router = router
        self._history = list(history or [])
        self._context = (context or ConversationContext()).model_copy(deep=True)
        self._operation_events: list[SummarizationEvent] = []
        self._facts_operation_events: list[FactsUpdateEvent] = []
        self._long_term_memory = list(long_term_memory or [])
        self._long_term_memory_loader = long_term_memory_loader
        self._context_window = context_window
        self._working_memory = list(working_memory or [])
        self._working_memory_store = working_memory_store
        self._session_id = session_id
        self._memory_classifier = memory_classifier
        self._memory_events: list[MemoryEvent] = []
        self._pending_memory = list(pending_memory or [])
        self._user_profile = user_profile
        self._invariants = list(invariants or [])
        self._strategy = context_strategy_for(
            config,
            router,
            facts,
            self._long_term_memory,
            self._context_window,
            self._working_memory,
            self._user_profile,
            self._invariants,
        )

    @property
    def history(self) -> list[ChatMessage]:
        return list(self._history)

    @property
    def context(self) -> ConversationContext:
        return self._context.model_copy(deep=True)

    @property
    def operation_events(self) -> list[SummarizationEvent]:
        return [event.model_copy(deep=True) for event in self._operation_events]

    @property
    def facts(self) -> dict[str, str]:
        return self._strategy.persistent_facts()

    @property
    def facts_operation_events(self) -> list[FactsUpdateEvent]:
        return [event.model_copy(deep=True) for event in self._facts_operation_events]

    @property
    def working_memory(self) -> list[WorkingMemoryItem]:
        return [item.model_copy(deep=True) for item in self._working_memory]

    @property
    def memory_events(self) -> list[MemoryEvent]:
        return [event.model_copy(deep=True) for event in self._memory_events]

    @property
    def pending_memory(self):
        return [item.model_copy(deep=True) for item in self._pending_memory]

    def set_invariants(self, invariants: list[Invariant]) -> None:
        self._invariants = list(invariants)
        self._strategy.set_invariants(self._invariants)
        if self._memory_classifier is not None:
            update_invariants = getattr(self._memory_classifier, "set_invariants", None)
            if callable(update_invariants):
                update_invariants(self._invariants)

    @property
    def has_long_term_memory(self) -> bool:
        return bool(self._long_term_memory)

    @property
    def has_sensitive_memory(self) -> bool:
        return bool(
            self._long_term_memory or self._working_memory or self._pending_memory or self.facts
        )

    def ask(
        self,
        content: str,
        *,
        agent_log_id: str | None = None,
        completion: Callable[[list[ChatMessage], LLMConfig], LLMResponse] | None = None,
    ) -> LLMResponse:
        self._refresh_long_term_memory()
        if self._pending_event() is not None:
            raise SummarizationRetryRequired(
                "Retry the failed summarization before sending another message"
            )

        self._operation_events = []
        self._facts_operation_events = []
        self._memory_events = []
        context_before_turn = self._context.model_copy(deep=True)
        facts_event_count = len(self._context.facts_events)
        self._history.append(
            ChatMessage(role="user", content=content, created_at=datetime.now(UTC))
        )
        self._memory_events.append(
            MemoryEvent(id=str(uuid.uuid4()), scope="short_term", action="saved")
        )
        self._classify_memory(content)
        try:
            self._strategy.update_after_user_message(self._history, self._context)
            self._facts_operation_events = [
                event.model_copy(deep=True)
                for event in self._context.facts_events[facts_event_count:]
            ]
            self._compact_eligible_messages()
        except SummarizationFailed:
            # The user message remains in the transcript so Retry can resume this turn.
            raise
        except FactsUpdateFailed as error:
            # Preserve the failed operation while rolling back the user turn.
            self._context = context_before_turn
            self._context.facts_events.append(error.event)
            self._history.pop()
            self._strategy.rollback_turn()
            raise
        except Exception:
            self._history.pop()
            self._context = context_before_turn
            self._strategy.rollback_turn()
            raise

        try:
            with agent_log_operation(
                "primary",
                provider=self.config.provider,
                model=self.config.model,
            ):
                response = (completion or self._router.complete)(
                    self._messages_for_request(), self.config
                )
        except Exception:
            self._history.pop()
            self._context = context_before_turn
            self._operation_events = []
            self._facts_operation_events = []
            self._strategy.rollback_turn()
            raise
        self._append_response(response, agent_log_id)
        self._strategy.commit_turn()
        return self._redact_long_term_trace(response)

    def retry_summarization(self, *, agent_log_id: str | None = None) -> LLMResponse:
        self._refresh_long_term_memory()
        event = self._pending_event()
        if event is None:
            raise SummarizationRetryRequired("There is no failed summarization to retry")
        if not self._history or self._history[-1].role != "user":
            raise SummarizationRetryRequired("The failed turn does not have a pending user message")

        self._operation_events = []
        context_before_retry = self._context.model_copy(deep=True)
        self._summarize(event)
        self._compact_eligible_messages()
        try:
            with agent_log_operation(
                "retry",
                provider=self.config.provider,
                model=self.config.model,
            ):
                response = self._router.complete(self._messages_for_request(), self.config)
        except Exception:
            self._context = context_before_retry
            self._operation_events = []
            raise
        self._append_response(response, agent_log_id)
        return self._redact_long_term_trace(response)

    def _compact_eligible_messages(self) -> None:
        policy = self.config.context_management
        if not policy.enabled or policy.strategy != ContextStrategyName.SUMMARY:
            return

        recent_message_count = policy.recent_exchange_limit * 2
        summary_batch_message_count = policy.summary_batch_exchange_count * 2
        while (
            len(self._history) - self._context.summarized_message_count - recent_message_count
            >= summary_batch_message_count
        ):
            start = self._context.summarized_message_count
            now = datetime.now(UTC)
            summarizer = self._summarizer_config()
            event = SummarizationEvent(
                id=str(uuid.uuid4()),
                status="failed",
                after_message_index=len(self._history) - 1,
                start_message_index=start,
                message_count=summary_batch_message_count,
                provider=summarizer.provider,
                model=summarizer.model,
                duration_seconds=0,
                created_at=now,
                updated_at=now,
            )
            self._context.events.append(event)
            self._summarize(event)

    def _summarize(self, event: SummarizationEvent) -> None:
        start = event.start_message_index
        end = start + event.message_count
        batch = self._history[start:end]
        if len(batch) != event.message_count:
            raise SummarizationRetryRequired(
                "The messages for this summarization are no longer available"
            )

        config = self._summarizer_config()
        payload = {
            "existing_summary": self._context.summary or None,
            "messages": [message.model_dump(include={"role", "content"}) for message in batch],
        }
        started_at = time.perf_counter()
        try:
            with agent_log_operation(
                "summarization",
                provider=config.provider,
                model=config.model,
            ):
                response = self._router.complete(
                    [
                        ChatMessage(
                            role="system",
                            content="\n\n".join(
                                part
                                for part in (
                                    config.system_prompt,
                                    render_invariants_context(self._invariants),
                                )
                                if part
                            ),
                        ),
                        ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
                    ],
                    config,
                )
            summary = response.content.strip()
            if not summary:
                raise ValueError("Summarizer returned an empty summary")
        except (ProviderError, ValueError) as error:
            event.status = "failed"
            event.duration_seconds = time.perf_counter() - started_at
            event.error = sanitize_error(str(error))
            event.trace = self._error_trace(error, redact=self.has_sensitive_memory)
            event.updated_at = datetime.now(UTC)
            self._operation_events.append(event.model_copy(deep=True))
            raise SummarizationFailed(event.model_copy(deep=True)) from error

        event.status = "completed"
        event.duration_seconds = time.perf_counter() - started_at
        event.usage = response.usage
        event.trace = (
            ProviderTrace.model_validate(sanitize_value(response.trace.model_dump()))
            if response.trace is not None
            else None
        )
        event.error = None
        event.updated_at = datetime.now(UTC)
        self._context.summary = summary
        self._context.summarized_message_count = end
        self._operation_events.append(event.model_copy(deep=True))

    def _summarizer_config(self) -> LLMConfig:
        summarizer = self.config.context_management.summarizer
        return LLMConfig(
            provider=summarizer.provider or self.config.provider,
            model=summarizer.model or self.config.model,
            system_prompt=summarizer.prompt,
            generation=summarizer.generation,
        )

    def _pending_event(self) -> SummarizationEvent | None:
        policy = self.config.context_management
        if not policy.enabled or policy.strategy != ContextStrategyName.SUMMARY:
            return None
        if self._context.events and self._context.events[-1].status == "failed":
            return self._context.events[-1]
        return None

    def _messages_for_request(self) -> list[ChatMessage]:
        messages = self._strategy.messages_for_request(self._history, self._context)
        invariant_context = render_invariants_context(self._invariants)
        if not invariant_context or any(
            message.role == "system" and invariant_context in message.content
            for message in messages
        ):
            return list(with_current_datetime_context(messages))
        if messages and messages[0].role == "system":
            messages[0] = messages[0].model_copy(
                update={"content": f"{messages[0].content}\n\n{invariant_context}"}
            )
        else:
            messages.insert(0, ChatMessage(role="system", content=invariant_context))
        return list(with_current_datetime_context(messages))

    def _append_response(self, response: LLMResponse, agent_log_id: str | None = None) -> None:
        self._history.append(
            ChatMessage(
                role="assistant",
                content=response.content,
                created_at=datetime.now(UTC),
                usage=response.usage,
                context_window=response.context_window,
                agent_log_id=agent_log_id,
            )
        )

    def _refresh_long_term_memory(self) -> None:
        if self._long_term_memory_loader is None:
            return
        facts = self._strategy.persistent_facts()
        self._long_term_memory = list(self._long_term_memory_loader())
        self._strategy = context_strategy_for(
            self.config,
            self._router,
            facts,
            self._long_term_memory,
            self._context_window,
            self._working_memory,
            self._user_profile,
            self._invariants,
        )

    def _classify_memory(self, content: str) -> None:
        if (
            self._memory_classifier is None
            or self._working_memory_store is None
            or self._session_id is None
        ):
            return
        MemoryCoordinator(
            self._memory_classifier,
            self._working_memory_store,
            self._session_id,
            self.config,
        ).classify_and_apply(
            content,
            self._history,
            self._working_memory,
            self._pending_memory,
            self._memory_events,
            self._apply_classified_memory,
        )

    def _apply_classified_memory(
        self,
        working_memory: list[WorkingMemoryItem],
        pending_memory: list[PendingMemorySuggestion],
        events: list[MemoryEvent],
        memory_details: dict[str, Any],
    ) -> None:
        self._working_memory = working_memory
        self._pending_memory = pending_memory
        self._memory_events.extend(event.model_copy(update=memory_details) for event in events)
        self._strategy = context_strategy_for(
            self.config,
            self._router,
            self.facts,
            self._long_term_memory,
            self._context_window,
            self._working_memory,
            user_profile=self._user_profile,
        )

    def _redact_long_term_trace(self, response: LLMResponse) -> LLMResponse:
        if response.trace is None:
            return response
        result = response.model_copy(deep=True)
        result.trace = ProviderTrace.model_validate(sanitize_value(response.trace.model_dump()))
        return result

    @staticmethod
    def _error_trace(error: Exception, *, redact: bool = False) -> ProviderTrace | None:
        if not isinstance(error, ProviderError):
            return None
        response_body = error.response_body
        if not isinstance(response_body, dict):
            response_body = {"raw": response_body}
        return ProviderTrace(
            status_code=error.status_code,
            request_body=sanitize_value(error.request_body),
            response_body=sanitize_value(response_body),
        )


class AgentFactory:
    def __init__(self, router: LLMRouter, profiles_repository: ProfilesSource) -> None:
        self._router = router
        self._profiles_repository = profiles_repository

    def profiles(self) -> dict[str, AgentConfig]:
        return self._profiles_repository.load()

    def create(self, config: AgentConfig) -> Agent:
        return Agent(config=config, router=self._router)

    def create_from_profile(self, profile_name: str) -> Agent:
        profiles = self.profiles()
        try:
            return self.create(profiles[profile_name])
        except KeyError as error:
            raise KeyError(f"Unknown profile: {profile_name}") from error
