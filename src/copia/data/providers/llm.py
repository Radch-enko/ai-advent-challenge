from __future__ import annotations

import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

import httpx

from ...domain.contracts import AgentLogSink
from ...domain.models.config import (
    ChatMessage,
    LLMConfig,
    LLMResponse,
    ProviderCapabilities,
    ProviderModel,
    ProviderName,
    ProviderTrace,
    ToolCall,
    ToolDefinition,
    ToolLoopMessage,
)
from .http_logging import install_http_logging, record_response, record_transport_error


class ProviderError(RuntimeError):
    """An error returned while communicating with an LLM provider."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        request_body: dict[str, Any] | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_body = request_body or {}
        self.response_body = response_body if response_body is not None else {"error": message}


class LLMProvider(ABC):
    capabilities: ProviderCapabilities

    @abstractmethod
    def complete(
        self,
        messages: list[ChatMessage | ToolLoopMessage],
        config: LLMConfig,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

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


class OpenAIProvider(LLMProvider):
    CHAT_URL = "https://api.openai.com/v1/chat/completions"
    MODELS_URL = "https://api.openai.com/v1/models"
    capabilities = ProviderCapabilities(
        provider=ProviderName.OPENAI,
        supported_parameters=["max_output_tokens", "temperature", "top_p"],
        supports_structured_output=True,
    )

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        log_store: AgentLogSink | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = client or httpx.Client(timeout=60.0)
        self._log_store = log_store
        if log_store is not None:
            install_http_logging(self._client, log_store)

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
        if not self._api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")

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
            request_payload["parallel_tool_calls"] = False
        generation = config.generation
        if generation.max_output_tokens is not None:
            request_payload["max_completion_tokens"] = generation.max_output_tokens
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
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        try:
            response = self._client.send(http_request)
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = _openai_tool_calls(message.get("tool_calls"))
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            if response is None and self._log_store is not None:
                record_transport_error(self._log_store, http_request, error)
            body: Any = None
            if response is not None:
                try:
                    body = response.json()
                except ValueError:
                    body = {"raw": response.text}
            raise ProviderError(
                f"OpenAI request failed: {error}",
                status_code=response.status_code if response is not None else 0,
                request_body=request_payload,
                response_body=body,
            ) from error
        finally:
            if response is not None and self._log_store is not None:
                record_response(self._log_store, response)

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
            provider=ProviderName.OPENAI,
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

    def list_models(self) -> list[ProviderModel]:
        if not self._api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        request = self._client.build_request(
            "GET", self.MODELS_URL, headers={"Authorization": f"Bearer {self._api_key}"}
        )
        response = None
        try:
            response = self._client.send(request)
            response.raise_for_status()
            return [ProviderModel(id=model["id"]) for model in response.json()["data"]]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            if response is None and self._log_store is not None:
                record_transport_error(self._log_store, request, error)
            raise ProviderError(f"OpenAI models request failed: {error}") from error
        finally:
            if response is not None and self._log_store is not None:
                record_response(self._log_store, response)


class GigaChatProvider(LLMProvider):
    MODELS_URL = "https://api.giga.chat/v1/models"
    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    CHAT_URL = "https://api.giga.chat/v1/chat/completions"
    capabilities = ProviderCapabilities(
        provider=ProviderName.GIGACHAT,
        supported_parameters=["max_output_tokens", "temperature", "top_p"],
        supports_structured_output=True,
    )

    def __init__(
        self,
        auth_key: str | None = None,
        scope: str | None = None,
        client: httpx.Client | None = None,
        log_store: AgentLogSink | None = None,
    ) -> None:
        self._auth_key = auth_key or os.getenv("GIGACHAT_AUTH_KEY")
        self._scope = scope or os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self._client = client or httpx.Client(timeout=60.0)
        self._log_store = log_store
        if log_store is not None:
            install_http_logging(self._client, log_store)
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
        except (httpx.HTTPError, KeyError, ValueError) as error:
            if response is None and self._log_store is not None:
                record_transport_error(self._log_store, request, error)
            raise ProviderError(f"GigaChat authentication failed: {error}") from error
        finally:
            if response is not None and self._log_store is not None:
                record_response(self._log_store, response)

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
            if response is None and self._log_store is not None:
                record_transport_error(self._log_store, http_request, error)
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
            if response is not None and self._log_store is not None:
                record_response(self._log_store, response)

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
            if response is None and self._log_store is not None:
                record_transport_error(self._log_store, request, error)
            raise ProviderError(f"GigaChat models request failed: {error}") from error
        finally:
            if response is not None and self._log_store is not None:
                record_response(self._log_store, response)
