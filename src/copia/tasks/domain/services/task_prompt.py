from collections.abc import Callable

from copia.invariants.domain.models.invariant import Invariant
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.structured_output_config import StructuredOutputConfig
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.services.context_strategy import render_invariants_context
from copia.tasks.domain.models._planner_response import _PlannerResponse
from copia.tasks.domain.models.task_validation_result import TaskValidationResult


def prompt_message(content: str) -> ChatMessage:
    return ChatMessage(role="user", content=content)


def system_messages(
    session: ChatSession,
    role_prompt: str,
    invariants: list[Invariant] | None,
    load_invariants: Callable[[], list[Invariant]],
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    if session.config.system_prompt:
        messages.append(ChatMessage(role="system", content=session.config.system_prompt))
    invariant_context = render_invariants_context(
        invariants if invariants is not None else load_invariants()
    )
    if invariant_context:
        messages.append(ChatMessage(role="system", content=invariant_context))
    messages.append(ChatMessage(role="system", content=role_prompt))
    return messages


def task_llm_config(
    session: ChatSession, *, structured_schema: dict[str, object] | None = None
) -> LLMConfig:
    return LLMConfig(
        provider=session.config.provider,
        model=session.config.model,
        system_prompt=session.config.system_prompt,
        generation=session.config.generation.model_copy(deep=True),
        structured_output=(
            StructuredOutputConfig(schema=structured_schema, strict=True)
            if structured_schema is not None
            else None
        ),
        provider_options=dict(session.config.provider_options),
    )


def plan_schema() -> dict[str, object]:
    return _PlannerResponse.model_json_schema()


def validation_schema() -> dict[str, object]:
    schema = TaskValidationResult.model_json_schema()
    schema["required"] = list(schema["properties"])
    return schema
