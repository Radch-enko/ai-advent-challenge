from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from copia.common.configuration import get_settings
from copia.common.observability import MAX_BODY_BYTES, http_body_capture_enabled
from copia.providers.data.http_logging import record_response, record_stream_response
from copia.providers.data.llm import (
    LLMProvider,
    _arguments,
    _stream_data,
    _structured_data,
    _usage,
)
from copia.providers.domain.errors import ProviderError
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.llm_stream_event import LLMStreamEvent
from copia.providers.domain.models.provider_capabilities import ProviderCapabilities
from copia.providers.domain.models.provider_model import ProviderModel
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.providers.domain.models.tool_call import ToolCall
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.providers.domain.models.tool_loop_message import ToolLoopMessage
from copia.sessions.domain.models.chat_message import ChatMessage


def _openai_message(message: ChatMessage | ToolLoopMessage) -> dict[str, Any]:
    if isinstance(message, ChatMessage):
        return message.model_dump(include={"role", "content"})
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.name is not None:
        payload["name"] = message.name
    return payload


def _openai_tool_calls(value: object) -> list[ToolCall]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProviderError("Provider returned invalid tool calls")
    calls: list[ToolCall] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("function"), dict):
            raise ProviderError("Provider returned invalid tool call")
        function = item["function"]
        call_id = item.get("id")
        name = function.get("name")
        if not isinstance(call_id, str) or not isinstance(name, str):
            raise ProviderError("Provider returned invalid tool call")
        calls.append(
            ToolCall(id=call_id, name=name, arguments=_arguments(function.get("arguments")))
        )
    return calls


class OpenAIProvider(LLMProvider):
    CHAT_URL = "https://api.openai.com/v1/chat/completions"
    MODELS_URL = "https://api.openai.com/v1/models"
    PROVIDER_NAME = ProviderName.OPENAI
    PROVIDER_LABEL = "OpenAI"
    MAX_TOKENS_PARAMETER = "max_completion_tokens"
    INCLUDE_STREAM_USAGE = True
    SEND_PARALLEL_TOOL_CALLS = True
    capabilities = ProviderCapabilities(
        provider=ProviderName.OPENAI,
        supported_parameters=["max_output_tokens", "temperature", "top_p"],
        supports_structured_output=True,
        supports_streaming=True,
    )

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        configured_key = get_settings().openai_api_key
        self._api_key = api_key or (
            configured_key.get_secret_value() if configured_key is not None else None
        )
        self._client = client or httpx.Client(timeout=60.0)

    def _require_configuration(self) -> None:
        if not self._api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")

    def _request_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    @staticmethod
    def _supports_sampling(model: str) -> bool:
        """Return model-level support instead of treating every GPT-5 model equally."""
        normalized = model.lower()
        unsupported_prefixes = (
            "gpt-5-mini-",
            "gpt-5-nano-",
            "gpt-5.1",
            "gpt-5.2",
            "gpt-6",
            "o1",
            "o3",
            "o4",
        )
        return normalized not in {
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
        } and not normalized.startswith(unsupported_prefixes)

    def complete(
        self,
        messages: list[ChatMessage | ToolLoopMessage],
        config: LLMConfig,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        self._require_configuration()

        request_payload: dict[str, Any] = {
            "model": config.model,
            "messages": [_openai_message(message) for message in messages],
        }
        if tools:
            request_payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.parameters or {"type": "object", "properties": {}},
                    },
                }
                for tool in tools
            ]
            request_payload["tool_choice"] = "auto"
            if self.SEND_PARALLEL_TOOL_CALLS:
                request_payload["parallel_tool_calls"] = False
        generation = config.generation
        if generation.max_output_tokens is not None:
            request_payload[self.MAX_TOKENS_PARAMETER] = generation.max_output_tokens
        if generation.temperature is not None and self._supports_sampling(config.model):
            request_payload["temperature"] = generation.temperature
        if generation.top_p is not None and self._supports_sampling(config.model):
            request_payload["top_p"] = generation.top_p
        if config.structured_output is not None:
            request_payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "copia_response",
                    "schema": config.structured_output.json_schema,
                    "strict": config.structured_output.strict,
                },
            }
        request_payload.update(config.provider_options)

        response = None
        http_request = self._client.build_request(
            "POST",
            self.CHAT_URL,
            json=request_payload,
            headers=self._request_headers(),
        )
        try:
            response = self._client.send(http_request)
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = _openai_tool_calls(message.get("tool_calls"))
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            body: Any = None
            if response is not None:
                try:
                    body = response.json()
                except ValueError:
                    body = {"raw": response.text}
            raise ProviderError(
                f"{self.PROVIDER_LABEL} request failed: {error}",
                status_code=response.status_code if response is not None else 0,
                request_body=request_payload,
                response_body=body,
            ) from error
        finally:
            if response is not None:
                record_response(response)

        usage = None
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = {
                key: value
                for key, value in raw_usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and isinstance(value, int)
            }
            prompt_details = raw_usage.get("prompt_tokens_details")
            if isinstance(prompt_details, dict) and isinstance(
                prompt_details.get("cached_tokens"), int
            ):
                usage["cached_prompt_tokens"] = prompt_details["cached_tokens"]
        return LLMResponse(
            content=content,
            provider=self.PROVIDER_NAME,
            model=data.get("model", config.model),
            usage=usage,
            structured_data=_structured_data(content, config.structured_output is not None),
            trace=ProviderTrace(
                status_code=response.status_code,
                request_body=request_payload,
                response_body=data,
            ),
            tool_calls=tool_calls,
        )

    def stream(
        self,
        messages: list[ChatMessage | ToolLoopMessage],
        config: LLMConfig,
        tools: list[ToolDefinition] | None = None,
    ) -> Iterator[LLMStreamEvent]:
        self._require_configuration()
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [_openai_message(message) for message in messages],
            "stream": True,
        }
        if self.INCLUDE_STREAM_USAGE:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.parameters or {"type": "object", "properties": {}},
                    },
                }
                for tool in tools
            ]
            payload["tool_choice"] = "auto"
            if self.SEND_PARALLEL_TOOL_CALLS:
                payload["parallel_tool_calls"] = False
        generation = config.generation
        if generation.max_output_tokens is not None:
            payload[self.MAX_TOKENS_PARAMETER] = generation.max_output_tokens
        if generation.temperature is not None and self._supports_sampling(config.model):
            payload["temperature"] = generation.temperature
        if generation.top_p is not None and self._supports_sampling(config.model):
            payload["top_p"] = generation.top_p
        if config.structured_output is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "copia_response",
                    "schema": config.structured_output.json_schema,
                    "strict": config.structured_output.strict,
                },
            }
        payload.update(config.provider_options)

        content: list[str] = []
        tool_deltas: dict[int, dict[str, Any]] = {}
        stream_events: list[dict[str, Any]] | None = [] if http_body_capture_enabled() else None
        stream_event_bytes = 16
        stream_events_truncated = False
        usage: dict[str, Any] | None = None
        response_model = config.model
        response: httpx.Response | None = None
        stream_response_body: dict[str, Any] | None = None
        try:
            with self._client.stream(
                "POST",
                self.CHAT_URL,
                json=payload,
                headers=self._request_headers(),
            ) as response:
                response.request.extensions["copia.otel.request.body"] = payload
                if response.is_error:
                    response.read()
                response.raise_for_status()
                for event in _stream_data(response):
                    if stream_events is not None and not stream_events_truncated:
                        event_size = len(json.dumps(event, ensure_ascii=True).encode("utf-8"))
                        event_size += 1 if stream_events else 0
                        if stream_event_bytes + event_size > MAX_BODY_BYTES:
                            stream_events.clear()
                            stream_events_truncated = True
                        else:
                            stream_events.append(event)
                            stream_event_bytes += event_size
                    if isinstance(event.get("model"), str):
                        response_model = event["model"]
                    usage = event.get("usage") or usage
                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") if isinstance(choice, dict) else None
                    if not isinstance(delta, dict):
                        continue
                    text = delta.get("content")
                    if isinstance(text, str) and text:
                        content.append(text)
                        yield LLMStreamEvent(kind="text_delta", text=text)
                    calls = delta.get("tool_calls")
                    if isinstance(calls, list):
                        for item in calls:
                            if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                                continue
                            index = item["index"]
                            current = tool_deltas.setdefault(
                                index,
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                },
                            )
                            if isinstance(item.get("id"), str):
                                current["id"] = item["id"]
                            function = item.get("function")
                            if isinstance(function, dict):
                                if isinstance(function.get("name"), str):
                                    current["function"]["name"] += function["name"]
                                if isinstance(function.get("arguments"), str):
                                    current["function"]["arguments"] += function["arguments"]
            raw_calls = [tool_deltas[index] for index in sorted(tool_deltas)]
            content_text = "".join(content)
            response_body = {
                "model": response_model,
                "choices": [{"message": {"content": content_text, "tool_calls": raw_calls}}],
                "usage": usage,
            }
            stream_response_body = response_body
            result = LLMResponse(
                content=content_text,
                provider=self.PROVIDER_NAME,
                model=response_model,
                usage=_usage(usage, "cached_tokens"),
                structured_data=_structured_data(
                    content_text, config.structured_output is not None
                ),
                trace=ProviderTrace(
                    status_code=response.status_code if response else 200,
                    request_body=payload,
                    response_body=response_body,
                ),
                tool_calls=_openai_tool_calls(raw_calls),
            )
            yield LLMStreamEvent(kind="completed", response=result)
        except ProviderError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(
                f"{self.PROVIDER_LABEL} stream failed: {error}",
                status_code=response.status_code if response else 0,
                request_body=payload,
            ) from error
        finally:
            if response is not None:
                record_stream_response(
                    response,
                    response_body=stream_response_body,
                    stream_events=stream_events,
                    stream_events_truncated=stream_events_truncated,
                )

    def list_models(self) -> list[ProviderModel]:
        self._require_configuration()
        request = self._client.build_request(
            "GET", self.MODELS_URL, headers=self._request_headers()
        )
        response = None
        try:
            response = self._client.send(request)
            response.raise_for_status()
            return [ProviderModel(id=model["id"]) for model in response.json()["data"]]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"{self.PROVIDER_LABEL} models request failed: {error}") from error
        finally:
            if response is not None:
                record_response(response)

    def close(self) -> None:
        self._client.close()
