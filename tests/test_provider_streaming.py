from __future__ import annotations

import json

import httpx

from copia.providers.data.llm import GigaChatProvider, LLMProvider, OpenAIProvider, _stream_data
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_capabilities import ProviderCapabilities
from copia.providers.domain.models.provider_model import ProviderModel
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.domain.models.chat_message import ChatMessage


def _sse(*events: dict) -> bytes:
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()


def test_provider_sse_parser_reads_data_lines_and_done() -> None:
    response = httpx.Response(
        200,
        content=b'data: {"choices":[]}\n\ndata: [DONE]\n\n',
        request=httpx.Request("POST", "https://provider.test"),
    )
    assert list(_stream_data(response)) == [{"choices": []}]


def test_openai_stream_normalizes_text_and_fragmented_tool_arguments() -> None:
    chunks = [
        {"model": "gpt-test", "choices": [{"delta": {"content": "hello "}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "function": {"name": "search", "arguments": '{"q":'},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"test"}'}}]}}
            ]
        },
        {"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 1}},
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_sse(*chunks), request=request)
        )
    )
    provider = OpenAIProvider(api_key="test", client=client)

    events = list(
        provider.stream(
            [ChatMessage(role="user", content="go")], LLMConfig(provider="openai", model="gpt-test")
        )
    )

    assert [event.text for event in events if event.kind == "text_delta"] == ["hello "]
    result = events[-1].response
    assert result is not None
    assert result.content == "hello "
    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].arguments == {"q": "test"}
    assert result.usage == {"prompt_tokens": 2, "completion_tokens": 1}


def test_gigachat_stream_normalizes_content() -> None:
    chunks = [
        {"choices": [{"delta": {"content": "Giga"}}]},
        {"choices": [{"delta": {"content": "Chat"}}]},
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_sse(*chunks), request=request)
        )
    )
    provider = GigaChatProvider(auth_key="test", client=client)
    provider._access_token = "access"
    provider._token_expires_at = 10**12

    events = list(
        provider.stream(
            [ChatMessage(role="user", content="go")],
            LLMConfig(provider="gigachat", model="GigaChat"),
        )
    )

    assert [event.text for event in events if event.kind == "text_delta"] == ["Giga", "Chat"]
    assert events[-1].response is not None
    assert events[-1].response.content == "GigaChat"


def test_provider_without_streaming_uses_one_text_event() -> None:
    class BasicProvider(LLMProvider):
        capabilities = ProviderCapabilities(
            provider=ProviderName.OPENAI, supported_parameters=[], supports_structured_output=False
        )

        def complete(self, messages, config, tools=None):
            return LLMResponse(
                content="full response", provider=ProviderName.OPENAI, model=config.model
            )

        def list_models(self):
            return [ProviderModel(id="test")]

    events = list(
        BasicProvider().stream(
            [ChatMessage(role="user", content="go")],
            LLMConfig(provider="openai", model="test"),
        )
    )
    assert [event.text for event in events if event.kind == "text_delta"] == ["full response"]
    assert events[-1].kind == "completed"
