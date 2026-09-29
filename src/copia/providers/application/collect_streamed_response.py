from collections.abc import Callable
from typing import Any

from copia.providers.application.llm_router import LLMRouter
from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.providers.domain.models.tool_loop_message import ToolLoopMessage
from copia.sessions.domain.models.chat_message import ChatMessage


def collect_streamed_response(
    router: LLMRouter,
    messages: list[ChatMessage | ToolLoopMessage],
    config: LLMConfig,
    emit: Callable[[str, dict[str, Any]], None],
    tools: list[ToolDefinition] | None = None,
) -> LLMResponse:
    result: LLMResponse | None = None
    for event in router.stream(messages, config, tools):
        if event.kind == "text_delta" and event.text:
            emit("message.delta", {"text": event.text})
        elif event.kind == "completed":
            result = event.response
    if result is None:
        raise ProviderError("Provider stream ended without a completed response")
    return result
