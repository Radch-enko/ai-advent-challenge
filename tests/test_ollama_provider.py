from __future__ import annotations

import json

import httpx
import pytest

from copia.common.configuration import CopiaSettings, get_settings
from copia.providers.application.llm_router import LLMRouter
from copia.providers.data.ollama_provider import OllamaProvider
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.structured_output_config import StructuredOutputConfig
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.sessions.domain.models.chat_message import ChatMessage


def test_ollama_url_defaults_to_placeholder(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    assert str(CopiaSettings().ollama_base_url).rstrip("/") == "https://ollama.example.invalid"


def test_ollama_url_comes_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://configured-ollama.example.invalid")

    provider = OllamaProvider(
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    )

    assert str(get_settings().ollama_base_url).rstrip("/") == "https://configured-ollama.example.invalid"
    assert provider.CHAT_URL == "https://configured-ollama.example.invalid/v1/chat/completions"


def test_ollama_url_rejects_credentials_and_paths(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://user:secret@ollama.example.invalid/v1")

    with pytest.raises(ValueError, match="OLLAMA_BASE_URL must be an HTTP origin") as error:
        get_settings()
    assert "secret" not in str(error.value)


def test_ollama_lists_models_without_cloud_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://ollama.example.invalid/v1/models"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"data": [{"id": "demo-model"}]})

    provider = OllamaProvider(
        base_url="https://ollama.example.invalid",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert [model.id for model in provider.list_models()] == ["demo-model"]


def test_ollama_complete_preserves_structured_output_and_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert "authorization" not in request.headers
        assert payload["max_tokens"] == 32
        assert payload["temperature"] == 0.2
        assert payload["tools"][0]["function"]["name"] == "lookup"
        assert "parallel_tool_calls" not in payload
        assert payload["response_format"]["json_schema"]["schema"] == {"type": "object"}
        return httpx.Response(
            200,
            json={
                "model": "demo-model",
                "choices": [
                    {
                        "message": {
                            "content": '{"ok": true}',
                            "tool_calls": [
                                {
                                    "id": "call-demo",
                                    "type": "function",
                                    "function": {"name": "lookup", "arguments": '{"key":"demo"}'},
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            },
        )

    provider = OllamaProvider(
        base_url="https://ollama.example.invalid",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    config = LLMConfig(
        provider="ollama",
        model="demo-model",
        generation={"max_output_tokens": 32, "temperature": 0.2},
        structured_output=StructuredOutputConfig(schema={"type": "object"}),
    )

    response = provider.complete(
        [ChatMessage(role="user", content="Use the demo lookup")],
        config,
        [ToolDefinition(name="lookup", parameters={"type": "object"})],
    )

    assert response.provider == ProviderName.OLLAMA
    assert response.structured_data == {"ok": True}
    assert response.tool_calls[0].arguments == {"key": "demo"}
    assert response.usage == {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}


def test_ollama_stream_uses_openai_compatible_events() -> None:
    events = [
        {"choices": [{"delta": {"content": "Demo "}}]},
        {"choices": [{"delta": {"content": "reply"}}]},
    ]
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert "stream_options" not in payload
        return httpx.Response(200, content=body.encode(), request=request)

    provider = OllamaProvider(
        base_url="https://ollama.example.invalid",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = list(
        provider.stream(
            [ChatMessage(role="user", content="Demo question")],
            LLMConfig(provider="ollama", model="demo-model"),
        )
    )

    assert [event.text for event in result if event.kind == "text_delta"] == ["Demo ", "reply"]
    assert result[-1].response is not None
    assert result[-1].response.provider == ProviderName.OLLAMA
    assert result[-1].response.content == "Demo reply"


def test_router_exposes_ollama_provider() -> None:
    router = LLMRouter(
        {ProviderName.OLLAMA: OllamaProvider(base_url="https://ollama.example.invalid")}
    )

    assert router.capabilities(ProviderName.OLLAMA).supports_structured_output
    router.close()
