from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Protocol

from .config import AgentConfig, ChatMessage, ContextStrategyName, LLMConfig, LLMResponse, ProviderTrace
from .session import ConversationContext, FactsUpdateEvent, SummarizationEvent
from ..services.context_strategy import FactsUpdateFailed, context_strategy_for
from ..services.router import LLMRouter, ProviderError


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
    ) -> None:
        self.config = config
        self._router = router
        self._history = list(history or [])
        self._context = (context or ConversationContext()).model_copy(deep=True)
        self._operation_events: list[SummarizationEvent] = []
        self._facts_operation_events: list[FactsUpdateEvent] = []
        self._strategy = context_strategy_for(config, router, facts)

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

    def ask(self, content: str) -> LLMResponse:
        if self._pending_event() is not None:
            raise SummarizationRetryRequired("Retry the failed summarization before sending another message")

        self._operation_events = []
        self._facts_operation_events = []
        context_before_turn = self._context.model_copy(deep=True)
        facts_event_count = len(self._context.facts_events)
        self._history.append(ChatMessage(role="user", content=content))
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
        except Exception:
            self._history.pop()
            self._context = context_before_turn
            self._strategy.rollback_turn()
            raise

        try:
            response = self._router.complete(self._strategy.messages_for_request(self._history, self._context), self.config)
        except Exception:
            self._history.pop()
            self._context = context_before_turn
            self._operation_events = []
            self._facts_operation_events = []
            self._strategy.rollback_turn()
            raise
        self._append_response(response)
        self._strategy.commit_turn()
        return response

    def retry_summarization(self) -> LLMResponse:
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
            response = self._router.complete(self._messages_for_request(), self.config)
        except Exception:
            self._context = context_before_retry
            self._operation_events = []
            raise
        self._append_response(response)
        return response

    def _compact_eligible_messages(self) -> None:
        policy = self.config.context_management
        if not policy.enabled or policy.strategy != ContextStrategyName.SUMMARY:
            return

        recent_message_count = policy.recent_exchange_limit * 2
        summary_batch_message_count = policy.summary_batch_exchange_count * 2
        while (
            len(self._history)
            - self._context.summarized_message_count
            - recent_message_count
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
            raise SummarizationRetryRequired("The messages for this summarization are no longer available")

        config = self._summarizer_config()
        payload = {
            "existing_summary": self._context.summary or None,
            "messages": [message.model_dump(include={"role", "content"}) for message in batch],
        }
        started_at = time.perf_counter()
        try:
            response = self._router.complete(
                [
                    ChatMessage(role="system", content=config.system_prompt or ""),
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
            event.error = str(error)
            event.trace = self._error_trace(error)
            event.updated_at = datetime.now(UTC)
            self._operation_events.append(event.model_copy(deep=True))
            raise SummarizationFailed(event.model_copy(deep=True)) from error

        event.status = "completed"
        event.duration_seconds = time.perf_counter() - started_at
        event.usage = response.usage
        event.trace = response.trace
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
        return self._strategy.messages_for_request(self._history, self._context)

    def _append_response(self, response: LLMResponse) -> None:
        self._history.append(ChatMessage(
            role="assistant",
            content=response.content,
            usage=response.usage,
            context_window=response.context_window,
        ))

    @staticmethod
    def _error_trace(error: Exception) -> ProviderTrace | None:
        if not isinstance(error, ProviderError):
            return None
        response_body = error.response_body
        if not isinstance(response_body, dict):
            response_body = {"raw": response_body}
        return ProviderTrace(
            status_code=error.status_code,
            request_body=error.request_body,
            response_body=response_body,
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
