from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

import httpx

from copia.providers.domain.errors import ProviderError
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.llm_stream_event import LLMStreamEvent
from copia.providers.domain.models.provider_capabilities import ProviderCapabilities
from copia.providers.domain.models.provider_model import ProviderModel
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.providers.domain.models.tool_loop_message import ToolLoopMessage
from copia.sessions.domain.models.chat_message import ChatMessage


def _stream_data(response: httpx.Response) -> Iterator[dict[str, Any]]:
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ProviderError("Provider returned invalid stream data") from error
        if not isinstance(value, dict):
            raise ProviderError("Provider returned invalid stream data")
        yield value


def _usage(raw_usage: object, cached_key: str) -> dict[str, int] | None:
    if not isinstance(raw_usage, dict):
        return None
    usage = {
        key: value
        for key, value in raw_usage.items()
        if key in {"prompt_tokens", "completion_tokens", "total_tokens"} and isinstance(value, int)
    }
    cached_tokens = raw_usage.get(cached_key)
    if isinstance(cached_tokens, int):
        usage["cached_prompt_tokens"] = cached_tokens
    return usage or None


class LLMProvider(ABC):
    capabilities: ProviderCapabilities

    def close(self) -> None:
        """Release provider-owned resources when the application shuts down."""
        return None

    @abstractmethod
    def complete(
        self,
        messages: list[ChatMessage | ToolLoopMessage],
        config: LLMConfig,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    def stream(
        self,
        messages: list[ChatMessage | ToolLoopMessage],
        config: LLMConfig,
        tools: list[ToolDefinition] | None = None,
    ) -> Iterator[LLMStreamEvent]:
        response = self.complete(messages, config, tools)
        if response.content:
            yield LLMStreamEvent(kind="text_delta", text=response.content)
        yield LLMStreamEvent(kind="completed", response=response)

    @abstractmethod
    def list_models(self) -> list[ProviderModel]:
        raise NotImplementedError


def _structured_data(content: str, enabled: bool) -> dict[str, Any] | list[Any] | None:
    if not enabled:
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise ProviderError("Provider returned invalid JSON for structured output") from error
    if not isinstance(value, (dict, list)):
        raise ProviderError("Structured output must be a JSON object or array")
    return value


def _arguments(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ProviderError("Provider returned invalid tool arguments")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise ProviderError("Provider returned invalid tool arguments") from error
    if not isinstance(decoded, dict):
        raise ProviderError("Provider tool arguments must be a JSON object")
    return decoded
