from __future__ import annotations

import json

import httpx

from copia.providers.data.ollama_provider import OllamaProvider
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.sessions.domain.models.chat_message import ChatMessage


def test_ollama_tool_request_omits_unsupported_tool_choice() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["tools"][0]["function"]["name"] == "lookup"
        assert "tool_choice" not in payload
        return httpx.Response(
            200,
            json={
                "model": "llama3.1:8b",
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": '{"query":"demo"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
        )

    provider = OllamaProvider(
        base_url="https://ollama.example.invalid",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = provider.complete(
        [ChatMessage(role="user", content="Look this up")],
        LLMConfig(provider="ollama", model="llama3.1:8b"),
        [ToolDefinition(name="lookup", parameters={"type": "object"})],
    )

    assert response.tool_calls[0].name == "lookup"
    assert response.tool_calls[0].arguments == {"query": "demo"}


def test_ollama_stream_tool_request_omits_unsupported_tool_choice() -> None:
    event = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"query":"demo"}',
                            },
                        }
                    ]
                }
            }
        ]
    }
    body = f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["tools"][0]["function"]["name"] == "lookup"
        assert "tool_choice" not in payload
        return httpx.Response(200, content=body.encode(), request=request)

    provider = OllamaProvider(
        base_url="https://ollama.example.invalid",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    events = list(
        provider.stream(
            [ChatMessage(role="user", content="Look this up")],
            LLMConfig(provider="ollama", model="llama3.1:8b"),
            [ToolDefinition(name="lookup", parameters={"type": "object"})],
        )
    )

    response = events[-1].response
    assert response is not None
    assert response.tool_calls[0].name == "lookup"
    assert response.tool_calls[0].arguments == {"query": "demo"}
