from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from copia.common.domain.services.prompt_builder import PromptBuilder
from copia.common.domain.services.prompt_resources import render_prompt
from copia.common.domain.services.runtime_context import render_current_datetime_context
from copia.sessions.domain.models.chat_message import ChatMessage


class LLMContextBuilder:
    """Build the exact chat messages sent to an LLM from named context inputs."""

    @staticmethod
    def build(
        *,
        history: Sequence[ChatMessage] = (),
        system_prompt: str | None = None,
        summary: str | None = None,
        invariants: str | None = None,
        current_time: datetime | None = None,
        user_profile: str | None = None,
        long_term_memory: str | None = None,
        working_memory: str | None = None,
        additional_system_context: str | None = None,
        role_prompt: str | None = None,
    ) -> list[ChatMessage]:
        if role_prompt is not None:
            messages = [
                ChatMessage(role="system", content=section)
                for section in (system_prompt, invariants, role_prompt)
                if section and section.strip()
            ]
            messages.extend(history)
            return _add_current_time(messages, current_time)

        builder = PromptBuilder().extend(
            (
                ("system_prompt", system_prompt),
                ("invariants", invariants),
                ("user_profile", user_profile),
                ("long_term_memory_precedence", _long_term_precedence(long_term_memory)),
                ("long_term_memory", long_term_memory),
                ("summary", summary),
                ("working_memory", working_memory),
                ("additional_system_context", additional_system_context),
            )
        )
        content = builder.build()
        messages = [ChatMessage(role="system", content=content)] if content else []
        messages.extend(history)
        return _add_current_time(messages, current_time)


def _add_current_time(
    messages: list[ChatMessage], current_time: datetime | None
) -> list[ChatMessage]:
    if current_time is None:
        return messages
    context = render_current_datetime_context(current_time)
    for index, message in enumerate(messages):
        if message.role == "system":
            messages[index] = message.model_copy(
                update={"content": f"{message.content}\n\n{context}"}
            )
            return messages
    messages.insert(0, ChatMessage(role="system", content=context))
    return messages


def _long_term_precedence(long_term_memory: str | None) -> str | None:
    if not long_term_memory:
        return None
    return render_prompt("copia.common", "long_term_memory_precedence.md")
