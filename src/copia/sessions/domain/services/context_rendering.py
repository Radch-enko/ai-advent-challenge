from __future__ import annotations

import json
import re
from math import ceil
from typing import TypeVar

from copia.agents.domain.models.agent_config import AgentConfig
from copia.common.domain.services.llm_context_builder import LLMContextBuilder
from copia.common.domain.services.prompt_resources import render_prompt
from copia.invariants.domain.models.invariant import Invariant
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.providers.domain.errors import ProviderError
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.security.domain.services.credential_sanitizer import sanitize_value
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.user_profiles.domain.models.user_profile import UserProfile
from copia.user_profiles.domain.services.profile_preferences import (
    profile_preferences_block_size,
    profile_preferences_json,
)

CONSERVATIVE_FALLBACK_CONTEXT_WINDOW = 4_096
TMemory = TypeVar("TMemory", LongTermMemoryItem, WorkingMemoryItem)


def _working_memory_context(items: list[WorkingMemoryItem]) -> str | None:
    if not items:
        return None
    values = json.dumps(
        [{"key": item.key, "value": item.value} for item in items], ensure_ascii=False
    )
    values = _escape_untrusted_prompt_text(values)
    return render_prompt("copia.sessions", "working_memory_context.md", memory=values)


def _escape_untrusted_prompt_text(value: str) -> str:
    return value.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_invariants_context(items: list[Invariant]) -> str | None:
    if not items:
        return None
    values = json.dumps(
        [{"name": item.name, "text": item.text} for item in items],
        ensure_ascii=False,
        indent=2,
    )
    values = _escape_untrusted_prompt_text(values)
    return render_prompt("copia.sessions", "invariants_context.md", invariants=values)


def _with_system_context(
    config: AgentConfig,
    long_term_memory: list[LongTermMemoryItem],
    working_context: str | None,
    history: list[ChatMessage],
    context_window: int | None,
    working_items: list[WorkingMemoryItem] | None = None,
    user_profile: UserProfile | None = None,
    invariants: list[Invariant] | None = None,
    summary: str | None = None,
) -> list[ChatMessage]:
    recent_keys = _keys_represented_by_transcript(history)
    effective_working = _latest_items(
        [item for item in (working_items or []) if item.key.lower() not in recent_keys]
    )
    effective_long_term = _latest_items(
        [item for item in long_term_memory if item.key.lower() not in recent_keys]
    )
    effective_long_term = [
        item
        for item in effective_long_term
        if item.key.lower() not in {item.key.lower() for item in effective_working}
    ]
    selected_long_term = _long_term_candidates(effective_long_term)
    while (
        _request_exceeds_context_window(
            _context_messages(
                config,
                selected_long_term,
                working_context,
                effective_working,
                history,
                user_profile,
                invariants,
                summary,
            ),
            config,
            context_window,
        )
        and selected_long_term
    ):
        selected_long_term.pop()
    while (
        _request_exceeds_context_window(
            _context_messages(
                config,
                selected_long_term,
                working_context,
                effective_working,
                history,
                user_profile,
                invariants,
                summary,
            ),
            config,
            context_window,
        )
        and effective_working
    ):
        effective_working.pop()
    long_term_block = (
        _render_long_term_memory_block(selected_long_term) if selected_long_term else None
    )
    rendered_working = _combined_working_context(working_context, effective_working)
    return LLMContextBuilder.build(
        system_prompt=config.system_prompt,
        invariants=render_invariants_context(invariants or []),
        user_profile=_render_user_profile_block(user_profile) if user_profile else None,
        long_term_memory=long_term_block,
        summary=summary,
        working_memory=rendered_working,
        history=history,
    )


def _context_messages(
    config: AgentConfig,
    long_term_items: list[dict[str, str]],
    working_context: str | None,
    working_items: list[WorkingMemoryItem],
    history: list[ChatMessage],
    user_profile: UserProfile | None = None,
    invariants: list[Invariant] | None = None,
    summary: str | None = None,
) -> list[ChatMessage]:
    long_term_block = _render_long_term_memory_block(long_term_items) if long_term_items else None
    rendered_working = _combined_working_context(working_context, working_items)
    return LLMContextBuilder.build(
        system_prompt=config.system_prompt,
        invariants=render_invariants_context(invariants or []),
        user_profile=_render_user_profile_block(user_profile) if user_profile else None,
        long_term_memory=long_term_block,
        summary=summary,
        working_memory=rendered_working,
        history=history,
    )


def _combined_working_context(prefix: str | None, items: list[WorkingMemoryItem]) -> str | None:
    item_context = _working_memory_context(items)
    return "\n\n".join(part for part in (prefix, item_context) if part) or None


def _latest_items(items: list[TMemory]) -> list[TMemory]:
    seen: set[str] = set()
    result = []
    for item in reversed(items):
        if item.key not in seen:
            seen.add(item.key)
            result.append(item)
    return list(reversed(result))


def _long_term_candidates(items: list[LongTermMemoryItem]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for category in ("decision", "profile", "knowledge"):
        for item in items:
            if item.category != category:
                continue
            candidate = [
                *selected,
                {"category": item.category, "key": item.key, "value": item.value},
            ]
            if len(_render_long_term_memory_block(candidate)) <= 6_000:
                selected = candidate
    return selected


def _keys_represented_by_transcript(history: list[ChatMessage]) -> set[str]:
    keys: set[str] = set()
    for message in history:
        keys.update(
            re.findall(
                r"(?:^|[\s,;])([A-Za-z_][\w-]*)\s*(?:[:=]|\bis\b)",
                message.content,
                re.I,
            )
        )
    return {key.lower() for key in keys}


def _bounded_long_term_memory_block(
    config: AgentConfig,
    items: list[LongTermMemoryItem],
    working_context: str | None,
    history: list[ChatMessage],
    context_window: int | None,
) -> str | None:
    maximum_characters = 6_000
    selected: list[dict[str, str]] = []
    for category in ("decision", "profile", "knowledge"):
        for item in items:
            if item.category != category:
                continue
            data = {"category": item.category, "key": item.key, "value": item.value}
            candidate = [*selected, data]
            block = _render_long_term_memory_block(candidate)
            if len(block) > maximum_characters:
                continue
            candidate_messages = LLMContextBuilder.build(
                system_prompt=config.system_prompt,
                long_term_memory=block,
                working_memory=working_context,
                history=history,
            )
            if _request_exceeds_context_window(candidate_messages, config, context_window):
                continue
            selected = candidate
    if not selected:
        return None
    return _render_long_term_memory_block(selected)


def _request_exceeds_context_window(
    messages: list[ChatMessage], config: AgentConfig, context_window: int | None
) -> bool:
    effective_context_window = context_window or CONSERVATIVE_FALLBACK_CONTEXT_WINDOW
    output_reserve = config.generation.max_output_tokens or 0
    estimated_input_tokens = sum(_estimated_message_tokens(message.content) for message in messages)
    return estimated_input_tokens + output_reserve > effective_context_window


def _estimated_message_tokens(content: str) -> int:
    ascii_characters = sum(character.isascii() for character in content)
    non_ascii_utf8_bytes = len(content.encode("utf-8")) - ascii_characters
    # ASCII uses a conservative 4:1 estimate; non-ASCII reserves each UTF-8 byte.
    return ceil(ascii_characters / 4) + non_ascii_utf8_bytes + 4


def _render_long_term_memory_block(items: list[dict[str, str]]) -> str:
    serialized_items = json.dumps(items, ensure_ascii=False, indent=2)
    # Keep the data valid JSON while preventing data values from closing the enclosing markup block.
    serialized_items = (
        serialized_items.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    return render_prompt("copia.sessions", "long_term_memory_context.md", memory=serialized_items)


def _render_user_profile_block(profile: UserProfile) -> str:
    values = _escape_untrusted_prompt_text(profile_preferences_json(profile))
    block = render_prompt("copia.sessions", "user_profile_context.md", preferences=values)
    if profile_preferences_block_size(profile) > 3_000:
        raise ValueError("User profile preferences exceed the prompt size limit")
    return block


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


def _redact_trace(trace: ProviderTrace | None) -> ProviderTrace | None:
    if trace is None:
        return None
    return trace.model_copy(
        update={
            "request_body": sanitize_value(trace.request_body),
            "response_body": sanitize_value(trace.response_body),
        }
    )
