import httpx

from copia.providers.data.llm import GigaChatProvider, OpenAIProvider
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.providers.domain.models.tool_loop_message import ToolLoopMessage
from copia.sessions.domain.models.chat_message import ChatMessage


def test_openai_serializes_tools_and_parses_tool_call() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "model",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_expenses",
                                        "arguments": '{"category":"food"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
        )

    provider = OpenAIProvider(
        api_key="test", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    response = provider.complete(
        [ChatMessage(role="user", content="search")],
        LLMConfig(provider=ProviderName.OPENAI, model="model"),
        [ToolDefinition(name="search_expenses", parameters={"type": "object"})],
    )

    assert captured["parallel_tool_calls"] is False
    assert captured["tools"][0]["function"]["name"] == "search_expenses"
    assert response.tool_calls[0].arguments == {"category": "food"}


def test_gigachat_serializes_function_result_and_parses_function_call() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth"):
            return httpx.Response(200, json={"access_token": "token", "expires_at": 9999999999999})
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "model",
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "function_call": {
                                "name": "search_expenses",
                                "arguments": {"category": "food"},
                            },
                        }
                    }
                ],
            },
        )

    provider = GigaChatProvider(
        auth_key="test", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    response = provider.complete(
        [
            ChatMessage(role="user", content="search"),
            ToolLoopMessage(role="tool", name="search_expenses", content='{"items":[]}'),
        ],
        LLMConfig(provider=ProviderName.GIGACHAT, model="model"),
        [ToolDefinition(name="search_expenses", parameters={"type": "object"})],
    )

    assert captured["function_call"] == "auto"
    assert captured["messages"][-1] == {
        "role": "function",
        "name": "search_expenses",
        "content": '{"items":[]}',
    }
    assert response.tool_calls[0].name == "search_expenses"
