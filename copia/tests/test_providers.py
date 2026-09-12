import httpx

from copia.domain.models.config import AgentConfig, ChatMessage, GenerationConfig, StructuredOutputConfig
from copia.data.providers.llm import GigaChatProvider, OpenAIProvider


def test_openai_maps_common_configuration() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"model": "test-model", "choices": [{"message": {"content": '{"ok": true}'}}], "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5, "prompt_tokens_details": {"cached_tokens": 1}}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = AgentConfig(
        name="test",
        provider="openai",
        model="test-model",
        generation=GenerationConfig(max_output_tokens=42, temperature=0.2, top_p=0.8),
        structured_output=StructuredOutputConfig(schema={"type": "object"}),
    )

    response = OpenAIProvider(api_key="key", client=client).complete([
        ChatMessage(
            role="user",
            content="Hello",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            context_window=100,
        ),
    ], config)

    assert captured["max_completion_tokens"] == 42
    assert captured["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert response.structured_data == {"ok": True}
    assert response.trace is not None
    assert response.trace.request_body == captured
    assert "name" not in response.trace.request_body
    assert captured["messages"] == [{"role": "user", "content": "Hello"}]
    assert response.usage == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
        "cached_prompt_tokens": 1,
    }


def test_openai_omits_sampling_for_gpt_five_models() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"model": "gpt-5-mini", "choices": [{"message": {"content": "Hello"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = AgentConfig(
        name="test",
        provider="openai",
        model="gpt-5-mini",
        generation=GenerationConfig(temperature=0.7, top_p=0.8),
    )

    OpenAIProvider(api_key="key", client=client).complete([ChatMessage(role="user", content="Hello")], config)

    assert "temperature" not in captured
    assert "top_p" not in captured


def test_openai_keeps_sampling_for_gpt_five_point_four() -> None:
    assert OpenAIProvider._supports_sampling("gpt-5.4-mini")


def test_gigachat_reuses_access_token() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "token", "expires_at": 9_999_999_999_000})
        return httpx.Response(
            200,
            json={
                "model": "GigaChat",
                "choices": [{"message": {"content": "Hello"}}],
                "usage": {
                    "prompt_tokens": 1,
                    "precached_prompt_tokens": 7,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    provider = GigaChatProvider(auth_key="key", client=httpx.Client(transport=httpx.MockTransport(handler)))
    config = AgentConfig(name="test", provider="gigachat", model="GigaChat")

    response = provider.complete([ChatMessage(role="user", content="One")], config)
    provider.complete([ChatMessage(role="user", content="Two")], config)

    assert len([call for call in calls if "oauth" in str(call.url)]) == 1
    assert calls[-1].headers["authorization"] == "Bearer token"
    assert response.trace is not None
    assert response.trace.status_code == 200
    assert response.trace.request_body["model"] == "GigaChat"
    assert response.usage == {
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
        "cached_prompt_tokens": 7,
    }
