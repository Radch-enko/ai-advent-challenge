from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx

from copia.common.configuration import get_settings
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


def _gigachat_message(message: ChatMessage | ToolLoopMessage) -> dict[str, Any]:
    if isinstance(message, ChatMessage):
        return message.model_dump(include={"role", "content"})
    if message.role == "assistant" and message.tool_calls:
        call = message.tool_calls[0]
        return {
            "role": "assistant",
            "content": message.content,
            "function_call": {"name": call.name, "arguments": call.arguments},
        }
    if message.role in {"tool", "function"}:
        return {"role": "function", "name": message.name, "content": message.content}
    return {"role": message.role, "content": message.content}


def _gigachat_tool_calls(value: object) -> list[ToolCall]:
    if value is None:
        return []
    if not isinstance(value, dict) or not isinstance(value.get("name"), str):
        raise ProviderError("Provider returned invalid function call")
    return [
        ToolCall(
            id=str(uuid.uuid4()),
            name=value["name"],
            arguments=_arguments(value.get("arguments", {})),
        )
    ]


class GigaChatProvider(LLMProvider):
    MODELS_URL = "https://api.giga.chat/v1/models"
    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    CHAT_URL = "https://api.giga.chat/v1/chat/completions"
    capabilities = ProviderCapabilities(
        provider=ProviderName.GIGACHAT,
        supported_parameters=["max_output_tokens", "temperature", "top_p"],
        supports_structured_output=True,
        supports_streaming=True,
    )

    def __init__(
        self,
        auth_key: str | None = None,
        scope: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        configured_key = settings.gigachat_auth_key
        self._auth_key = auth_key or (
            configured_key.get_secret_value() if configured_key is not None else None
        )
        self._scope = scope or settings.gigachat_scope
        self._client = client or httpx.Client(timeout=60.0)
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def _token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        if not self._auth_key:
            raise ProviderError("GIGACHAT_AUTH_KEY is not configured")

        response = None
        request = self._client.build_request(
            "POST",
            self.OAUTH_URL,
            data={"scope": self._scope},
            headers={
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {self._auth_key}",
            },
        )
        try:
            response = self._client.send(request)
            response.raise_for_status()
            data = response.json()
            token = data["access_token"]
            if not isinstance(token, str) or not token:
                raise ValueError("GigaChat authentication returned an invalid token")
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise ProviderError(f"GigaChat authentication failed: {error}") from error
        finally:
            if response is not None:
                record_response(response)

        expires_at = data.get("expires_at")
        if isinstance(expires_at, (int, float)):
            # GigaChat returns Unix time in milliseconds.
            self._token_expires_at = (expires_at / 1000) - 60
        else:
            self._token_expires_at = time.time() + 25 * 60
        self._access_token = token
        return token

    def complete(
        self,
        messages: list[ChatMessage | ToolLoopMessage],
        config: LLMConfig,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [_gigachat_message(message) for message in messages],
        }
        if tools:
            payload["functions"] = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.parameters or {"type": "object", "properties": {}},
                }
                for tool in tools
            ]
            payload["function_call"] = "auto"
        generation = config.generation
        if generation.max_output_tokens is not None:
            payload["max_tokens"] = generation.max_output_tokens
        if generation.temperature is not None:
            payload["temperature"] = generation.temperature
        if generation.top_p is not None:
            payload["top_p"] = generation.top_p
        if config.structured_output is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "schema": config.structured_output.json_schema,
                "strict": config.structured_output.strict,
            }
        payload.update(config.provider_options)

        response = None
        http_request = self._client.build_request(
            "POST",
            self.CHAT_URL,
            json=payload,
            headers={"Authorization": f"Bearer {self._token()}"},
        )
        try:
            response = self._client.send(http_request)
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = _gigachat_tool_calls(message.get("function_call"))
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            body: Any = None
            if response is not None:
                try:
                    body = response.json()
                except ValueError:
                    body = {"raw": response.text}
            raise ProviderError(
                f"GigaChat request failed: {error}",
                status_code=response.status_code if response is not None else 0,
                request_body=payload,
                response_body=body,
            ) from error
        finally:
            if response is not None:
                record_response(response)

        raw_usage = data.get("usage")
        usage = None
        if isinstance(raw_usage, dict):
            usage = {
                key: value
                for key, value in raw_usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and isinstance(value, int)
            }
            if isinstance(raw_usage.get("precached_prompt_tokens"), int):
                usage["cached_prompt_tokens"] = raw_usage["precached_prompt_tokens"]
        return LLMResponse(
            content=content,
            provider=ProviderName.GIGACHAT,
            model=data.get("model", config.model),
            usage=usage,
            structured_data=_structured_data(content, config.structured_output is not None),
            trace=ProviderTrace(
                status_code=response.status_code, request_body=payload, response_body=data
            ),
            tool_calls=tool_calls,
        )

    def stream(
        self,
        messages: list[ChatMessage | ToolLoopMessage],
        config: LLMConfig,
        tools: list[ToolDefinition] | None = None,
    ) -> Iterator[LLMStreamEvent]:
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [_gigachat_message(message) for message in messages],
            "stream": True,
        }
        if tools:
            payload["functions"] = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.parameters or {"type": "object", "properties": {}},
                }
                for tool in tools
            ]
            payload["function_call"] = "auto"
        generation = config.generation
        if generation.max_output_tokens is not None:
            payload["max_tokens"] = generation.max_output_tokens
        if generation.temperature is not None:
            payload["temperature"] = generation.temperature
        if generation.top_p is not None:
            payload["top_p"] = generation.top_p
        if config.structured_output is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "schema": config.structured_output.json_schema,
                "strict": config.structured_output.strict,
            }
        payload.update(config.provider_options)

        content: list[str] = []
        function_call: dict[str, str] = {"name": "", "arguments": ""}
        has_function_call = False
        usage: dict[str, Any] | None = None
        response_model = config.model
        response: httpx.Response | None = None
        try:
            with self._client.stream(
                "POST",
                self.CHAT_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._token()}"},
            ) as response:
                response.raise_for_status()
                for event in _stream_data(response):
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
                    call_delta = delta.get("function_call")
                    if isinstance(call_delta, dict):
                        has_function_call = True
                        for key in ("name", "arguments"):
                            if isinstance(call_delta.get(key), str):
                                function_call[key] += call_delta[key]
            content_text = "".join(content)
            response_body: dict[str, Any] = {
                "model": response_model,
                "choices": [{"message": {"content": content_text, "function_call": function_call}}],
                "usage": usage,
            }
            result = LLMResponse(
                content=content_text,
                provider=ProviderName.GIGACHAT,
                model=response_model,
                usage=_usage(usage, "precached_prompt_tokens"),
                structured_data=_structured_data(
                    content_text, config.structured_output is not None
                ),
                trace=ProviderTrace(
                    status_code=response.status_code if response else 200,
                    request_body=payload,
                    response_body=response_body,
                ),
                tool_calls=_gigachat_tool_calls(function_call) if has_function_call else [],
            )
            yield LLMStreamEvent(kind="completed", response=result)
        except ProviderError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(
                f"GigaChat stream failed: {error}",
                status_code=response.status_code if response else 0,
                request_body=payload,
            ) from error
        finally:
            if response is not None:
                record_stream_response(response)

    def list_models(self) -> list[ProviderModel]:
        request = self._client.build_request(
            "GET", self.MODELS_URL, headers={"Authorization": f"Bearer {self._token()}"}
        )
        response = None
        try:
            response = self._client.send(request)
            response.raise_for_status()
            data = response.json().get("data", [])
            return [ProviderModel(id=item["id"]) for item in data if item.get("type") == "chat"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"GigaChat models request failed: {error}") from error
        finally:
            if response is not None:
                record_response(response)

    def close(self) -> None:
        self._client.close()
