from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Protocol

from copia.agents.domain.models.agent_config import AgentConfig
from copia.common.domain.services.llm_context_builder import LLMContextBuilder
from copia.common.domain.services.prompt_resources import render_prompt
from copia.invariants.domain.models.invariant import Invariant
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.providers.domain.errors import ProviderError
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.structured_output_config import StructuredOutputConfig
from copia.security.domain.services.credential_sanitizer import sanitize_error
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.context_strategy_name import ContextStrategyName
from copia.sessions.domain.models.conversation_context import ConversationContext
from copia.sessions.domain.models.facts_update_event import FactsUpdateEvent
from copia.sessions.domain.services.context_rendering import (
    _error_trace,
    _escape_untrusted_prompt_text,
    _redact_trace,
    _with_system_context,
    render_invariants_context,
)
from copia.user_profiles.domain.models.user_profile import UserProfile

CONSERVATIVE_FALLBACK_CONTEXT_WINDOW = 4_096


class FactsUpdateFailed(RuntimeError):
    def __init__(self, event: FactsUpdateEvent) -> None:
        super().__init__(event.error or "Facts update failed")
        self.event = event


class LLMCompleter(Protocol):
    def complete(self, messages: list[ChatMessage], config: LLMConfig) -> LLMResponse: ...


class ContextStrategy(Protocol):
    """Update strategy memory and build one provider-agnostic LLM request."""

    def update_after_user_message(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> None: ...

    def messages_for_request(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> list[ChatMessage]: ...

    def set_invariants(self, invariants: list[Invariant]) -> None: ...

    def commit_turn(self) -> None: ...

    def rollback_turn(self) -> None: ...

    def persistent_facts(self) -> dict[str, str]: ...


class FullTranscriptStrategy:
    def __init__(
        self,
        config: AgentConfig,
        long_term_memory: list[LongTermMemoryItem],
        context_window: int | None,
        working_memory: list[WorkingMemoryItem] | None = None,
        user_profile: UserProfile | None = None,
        invariants: list[Invariant] | None = None,
    ) -> None:
        self._config = config
        self._long_term_memory = long_term_memory
        self._context_window = context_window
        self._working_memory = working_memory or []
        self._user_profile = user_profile
        self._invariants = invariants or []

    def update_after_user_message(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> None:
        pass

    def messages_for_request(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> list[ChatMessage]:
        return _with_system_context(
            self._config,
            self._long_term_memory,
            None,
            history,
            self._context_window,
            self._working_memory,
            user_profile=self._user_profile,
            invariants=self._invariants,
        )

    def commit_turn(self) -> None:
        pass

    def rollback_turn(self) -> None:
        pass

    def set_invariants(self, invariants: list[Invariant]) -> None:
        self._invariants = list(invariants)

    def persistent_facts(self) -> dict[str, str]:
        return {}


class SlidingWindowStrategy:
    def __init__(
        self,
        config: AgentConfig,
        long_term_memory: list[LongTermMemoryItem],
        context_window: int | None,
        working_memory: list[WorkingMemoryItem] | None = None,
        user_profile: UserProfile | None = None,
        invariants: list[Invariant] | None = None,
    ) -> None:
        self._config = config
        self._message_limit = config.context_management.recent_message_limit
        self._long_term_memory = long_term_memory
        self._context_window = context_window
        self._working_memory = working_memory or []
        self._user_profile = user_profile
        self._invariants = invariants or []

    def update_after_user_message(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> None:
        pass

    def messages_for_request(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> list[ChatMessage]:
        return _with_system_context(
            self._config,
            self._long_term_memory,
            None,
            history[-self._message_limit :],
            self._context_window,
            self._working_memory,
            user_profile=self._user_profile,
            invariants=self._invariants,
        )

    def commit_turn(self) -> None:
        pass

    def rollback_turn(self) -> None:
        pass

    def set_invariants(self, invariants: list[Invariant]) -> None:
        self._invariants = list(invariants)

    def persistent_facts(self) -> dict[str, str]:
        return {}


class BranchingStrategy(FullTranscriptStrategy):
    """Send the complete transcript stored in this independently forked session."""


class SummaryStrategy:
    """Legacy day-09 request projection; summary updates remain in Agent for now."""

    def __init__(
        self,
        config: AgentConfig,
        long_term_memory: list[LongTermMemoryItem],
        context_window: int | None,
        working_memory: list[WorkingMemoryItem] | None = None,
        user_profile: UserProfile | None = None,
        invariants: list[Invariant] | None = None,
    ) -> None:
        self._config = config
        self._long_term_memory = long_term_memory
        self._context_window = context_window
        self._working_memory = working_memory or []
        self._user_profile = user_profile
        self._invariants = invariants or []

    def update_after_user_message(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> None:
        pass

    def messages_for_request(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> list[ChatMessage]:
        summary_context = (
            render_prompt(
                "copia.sessions",
                "context_sections.md",
                summary=_escape_untrusted_prompt_text(context.summary),
            )
            if context.summary
            else None
        )
        messages = _with_system_context(
            self._config,
            self._long_term_memory,
            None,
            history[context.summarized_message_count :],
            self._context_window,
            self._working_memory,
            self._user_profile,
            self._invariants,
            summary=summary_context,
        )
        return messages

    def commit_turn(self) -> None:
        pass

    def rollback_turn(self) -> None:
        pass

    def set_invariants(self, invariants: list[Invariant]) -> None:
        self._invariants = list(invariants)

    def persistent_facts(self) -> dict[str, str]:
        return {}


class StickyFactsStrategy:
    def __init__(
        self,
        config: AgentConfig,
        router: LLMCompleter,
        facts: dict[str, str],
        long_term_memory: list[LongTermMemoryItem],
        context_window: int | None,
        working_memory: list[WorkingMemoryItem] | None = None,
        user_profile: UserProfile | None = None,
        invariants: list[Invariant] | None = None,
    ) -> None:
        self._config = config
        self._router = router
        self._facts = dict(facts)
        self._candidate_facts: dict[str, str] | None = None
        self._long_term_memory = long_term_memory
        self._context_window = context_window
        self._working_memory = working_memory or []
        self._user_profile = user_profile
        self._invariants = invariants or []

    def update_after_user_message(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> None:
        updater_config = self._updater_config()
        now = datetime.now(UTC)
        event = FactsUpdateEvent(
            id=str(uuid.uuid4()),
            status="failed",
            after_message_index=len(history) - 1,
            provider=updater_config.provider,
            model=updater_config.model,
            duration_seconds=0,
            created_at=now,
            updated_at=now,
        )
        previous_assistant = (
            history[-2].content if len(history) >= 2 and history[-2].role == "assistant" else None
        )
        payload = {
            "existing_facts": self._facts,
            "previous_assistant_message": previous_assistant,
            "current_user_message": history[-1].content,
        }
        started_at = time.perf_counter()
        try:
            response = self._router.complete(
                LLMContextBuilder.build(
                    system_prompt=updater_config.system_prompt,
                    invariants=render_invariants_context(self._invariants),
                    history=[
                        ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False))
                    ],
                ),
                updater_config,
            )
            updates, deletions = self._changes_from_response(response.structured_data)
        except (ProviderError, ValueError) as error:
            event.duration_seconds = time.perf_counter() - started_at
            event.error = sanitize_error(str(error))
            event.trace = _error_trace(
                error, redact=bool(self._long_term_memory or self._working_memory or self._facts)
            )
            event.updated_at = datetime.now(UTC)
            context.facts_events.append(event)
            raise FactsUpdateFailed(event) from error

        candidate = dict(self._facts)
        for key in deletions:
            candidate.pop(key, None)
        candidate.update(updates)
        self._candidate_facts = candidate
        event.status = "completed"
        event.updates = updates
        event.deletions = deletions
        event.duration_seconds = time.perf_counter() - started_at
        event.usage = response.usage
        event.trace = _redact_trace(response.trace)
        event.updated_at = datetime.now(UTC)
        context.facts_events.append(event)

    def messages_for_request(
        self,
        history: list[ChatMessage],
        context: ConversationContext,
    ) -> list[ChatMessage]:
        facts = self._candidate_facts if self._candidate_facts is not None else self._facts
        working_context = render_prompt(
            "copia.sessions",
            "facts_context.md",
            facts=_escape_untrusted_prompt_text(json.dumps(facts, ensure_ascii=False, indent=2)),
        )
        messages = _with_system_context(
            self._config,
            [item for item in self._long_term_memory if item.key not in facts],
            working_context,
            history[-self._config.context_management.recent_message_limit :],
            self._context_window,
            self._working_memory,
            self._user_profile,
            self._invariants,
        )
        return messages

    def commit_turn(self) -> None:
        if self._candidate_facts is not None:
            self._facts = self._candidate_facts
        self._candidate_facts = None

    def rollback_turn(self) -> None:
        self._candidate_facts = None

    def set_invariants(self, invariants: list[Invariant]) -> None:
        self._invariants = list(invariants)

    def persistent_facts(self) -> dict[str, str]:
        return dict(self._facts)

    def _updater_config(self) -> LLMConfig:
        updater = self._config.context_management.facts_updater
        return LLMConfig(
            provider=updater.provider or self._config.provider,
            model=updater.model or self._config.model,
            system_prompt=updater.prompt,
            generation=updater.generation,
            structured_output=StructuredOutputConfig(
                schema={
                    "type": "object",
                    "properties": {
                        "updates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string"},
                                    "value": {"type": "string"},
                                },
                                "required": ["key", "value"],
                                "additionalProperties": False,
                            },
                        },
                        "deletions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["updates", "deletions"],
                    "additionalProperties": False,
                }
            ),
        )

    @staticmethod
    def _changes_from_response(data: object) -> tuple[dict[str, str], list[str]]:
        if not isinstance(data, dict):
            raise ValueError("Facts updater returned invalid structured data")
        raw_updates = data.get("updates")
        raw_deletions = data.get("deletions")
        if not isinstance(raw_updates, list) or not isinstance(raw_deletions, list):
            raise ValueError("Facts updater response is missing updates or deletions")
        updates: dict[str, str] = {}
        for item in raw_updates:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("key"), str)
                or not isinstance(item.get("value"), str)
            ):
                raise ValueError("Facts updater returned an invalid update")
            updates[item["key"]] = item["value"]
        if not all(isinstance(key, str) for key in raw_deletions):
            raise ValueError("Facts updater returned an invalid deletion")
        return updates, raw_deletions


def context_strategy_for(
    config: AgentConfig,
    router: LLMCompleter | None = None,
    facts: dict[str, str] | None = None,
    long_term_memory: list[LongTermMemoryItem] | None = None,
    context_window: int | None = None,
    working_memory: list[WorkingMemoryItem] | None = None,
    user_profile: UserProfile | None = None,
    invariants: list[Invariant] | None = None,
) -> ContextStrategy:
    long_term_memory = long_term_memory or []
    working_memory = working_memory or []
    invariants = invariants or []
    if not config.context_management.enabled:
        return FullTranscriptStrategy(
            config,
            long_term_memory,
            context_window,
            working_memory,
            user_profile=user_profile,
            invariants=invariants,
        )
    if config.context_management.strategy == ContextStrategyName.SLIDING_WINDOW:
        return SlidingWindowStrategy(
            config,
            long_term_memory,
            context_window,
            working_memory,
            user_profile=user_profile,
            invariants=invariants,
        )
    if config.context_management.strategy == ContextStrategyName.STICKY_FACTS:
        if router is None:
            raise ValueError("Sticky Facts requires an LLM router")
        return StickyFactsStrategy(
            config,
            router,
            facts or {},
            long_term_memory,
            context_window,
            working_memory,
            user_profile=user_profile,
            invariants=invariants,
        )
    if config.context_management.strategy == ContextStrategyName.BRANCHING:
        return BranchingStrategy(
            config,
            long_term_memory,
            context_window,
            working_memory,
            user_profile=user_profile,
            invariants=invariants,
        )
    return SummaryStrategy(
        config,
        long_term_memory,
        context_window,
        working_memory,
        user_profile=user_profile,
        invariants=invariants,
    )
