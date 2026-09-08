from __future__ import annotations

import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

import httpx

from ...domain.models.config import ChatMessage, LLMConfig, LLMResponse, ProviderCapabilities, ProviderModel, ProviderName, ProviderTrace


class ProviderError(RuntimeError):
    """An error returned while communicating with an LLM provider."""

    def __init__(self, message: str, *, status_code: int = 0, request_body: dict[str, Any] | None = None, response_body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_body = request_body or {}
        self.response_body = response_body if response_body is not None else {"error": message}


class LLMProvider(ABC):
    capabilities: ProviderCapabilities

    @abstractmethod
    def complete(self, messages: list[ChatMessage], config: LLMConfig) -> LLMResponse:
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


class OpenAIProvider(LLMProvider):
    CHAT_URL = "https://api.openai.com/v1/chat/completions"
    MODELS_URL = "https://api.openai.com/v1/models"
    capabilities = ProviderCapabilities(
        provider=ProviderName.OPENAI,
        supported_parameters=["max_output_tokens", "temperature", "top_p"],
        supports_structured_output=True,
    )

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = client or httpx.Client(timeout=60.0)

    @staticmethod
    def _supports_sampling(model: str) -> bool:
        """Return model-level support instead of treating every GPT-5 model equally."""
        normalized = model.lower()
        unsupported_prefixes = ("gpt-5-mini-", "gpt-5-nano-", "gpt-5.1", "gpt-5.2", "gpt-6", "o1", "o3", "o4")
        return normalized not in {"gpt-5", "gpt-5-mini", "gpt-5-nano"} and not normalized.startswith(unsupported_prefixes)

    def complete(self, messages: list[ChatMessage], config: LLMConfig) -> LLMResponse:
        if not self._api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")

        request: dict[str, Any] = {
            "model": config.model,
            "messages": [message.model_dump() for message in messages],
        }
        generation = config.generation
        if generation.max_output_tokens is not None:
            request["max_completion_tokens"] = generation.max_output_tokens
        if generation.temperature is not None and self._supports_sampling(config.model):
            request["temperature"] = generation.temperature
        if generation.top_p is not None and self._supports_sampling(config.model):
            request["top_p"] = generation.top_p
        if config.structured_output is not None:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "copia_response",
                    "schema": config.structured_output.json_schema,
                    "strict": config.structured_output.strict,
                },
            }
        request.update(config.provider_options)

        response = None
        try:
            response = self._client.post(
                self.CHAT_URL,
                json=request,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            body: Any = None
            if response is not None:
                try:
                    body = response.json()
                except ValueError:
                    body = {"raw": response.text}
            raise ProviderError(
                f"OpenAI request failed: {error}",
                status_code=response.status_code if response is not None else 0,
                request_body=request,
                response_body=body,
            ) from error

        usage = None
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = {
                key: value for key, value in raw_usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"} and isinstance(value, int)
            }
        return LLMResponse(
            content=content,
            provider=ProviderName.OPENAI,
            model=data.get("model", config.model),
            usage=usage,
            structured_data=_structured_data(content, config.structured_output is not None),
            trace=ProviderTrace(
                status_code=response.status_code,
                request_body=request,
                response_body=data,
            ),
        )

    def list_models(self) -> list[ProviderModel]:
        if not self._api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        try:
            response = self._client.get(
                self.MODELS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            return [ProviderModel(id=model["id"]) for model in response.json()["data"]]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"OpenAI models request failed: {error}") from error


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
    ) -> None:
        self._auth_key = auth_key or os.getenv("GIGACHAT_AUTH_KEY")
        self._scope = scope or os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self._client = client or httpx.Client(timeout=60.0)
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def _token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        if not self._auth_key:
            raise ProviderError("GIGACHAT_AUTH_KEY is not configured")

        response = None
        try:
            response = self._client.post(
                self.OAUTH_URL,
                data={"scope": self._scope},
                headers={
                    "Accept": "application/json",
                    "RqUID": str(uuid.uuid4()),
                    "Authorization": f"Basic {self._auth_key}",
                },
            )
            response.raise_for_status()
            data = response.json()
            token = data["access_token"]
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise ProviderError(f"GigaChat authentication failed: {error}") from error

        expires_at = data.get("expires_at")
        if isinstance(expires_at, (int, float)):
            # GigaChat returns Unix time in milliseconds.
            self._token_expires_at = (expires_at / 1000) - 60
        else:
            self._token_expires_at = time.time() + 25 * 60
        self._access_token = token
        return token

    def complete(self, messages: list[ChatMessage], config: LLMConfig) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [message.model_dump() for message in messages],
        }
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
        try:
            response = self._client.post(
                self.CHAT_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._token()}"},
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"] or ""
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

        raw_usage = data.get("usage")
        usage = None
        if isinstance(raw_usage, dict):
            usage = {
                key: value
                for key, value in raw_usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and isinstance(value, int)
            }
        return LLMResponse(
            content=content,
            provider=ProviderName.GIGACHAT,
            model=data.get("model", config.model),
            usage=usage,
            structured_data=_structured_data(content, config.structured_output is not None),
            trace=ProviderTrace(status_code=response.status_code, request_body=payload, response_body=data),
        )

    def list_models(self) -> list[ProviderModel]:
        try:
            response = self._client.get(self.MODELS_URL, headers={"Authorization": f"Bearer {self._token()}"})
            response.raise_for_status()
            data = response.json().get("data", [])
            return [ProviderModel(id=item["id"]) for item in data if item.get("type") == "chat"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"GigaChat models request failed: {error}") from error
