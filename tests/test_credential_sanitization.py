from copia.agents.application.agent_runtime import Agent
from copia.agents.domain.models.agent_config import AgentConfig
from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.security.domain.services.credential_sanitizer import sanitize_value
from copia.service import _safe_trace, provider_error_detail


def test_primary_summarization_and_error_traces_sanitize_only_credentials() -> None:
    trace = ProviderTrace(
        status_code=502,
        request_body={
            "profile": "Alice",
            "facts": {"city": "Berlin"},
            "api_key": "s" + "k-trace-secret",
            "url": "https://provider.test?token=url-secret",
        },
        response_body={"working_memory": "finish report", "authorization": "Bearer secret"},
    )
    config = AgentConfig(name="test", provider="openai", model="model")
    response = LLMResponse(content="ok", provider="openai", model="model", trace=trace)
    sanitized = Agent(config=config, router=object())._redact_long_term_trace(response)

    assert sanitized.trace is not None
    assert sanitized.trace.request_body["profile"] == "Alice"
    assert sanitized.trace.request_body["facts"] == {"city": "Berlin"}
    assert sanitized.trace.request_body["api_key"] == "[REDACTED]"
    assert sanitized.trace.request_body["url"] == "https://provider.test?token=[REDACTED]"
    assert sanitized.trace.response_body["working_memory"] == "finish report"
    assert sanitized.trace.response_body["authorization"] == "[REDACTED]"

    assert _safe_trace(trace) is None
    detail = provider_error_detail(
        ProviderError(
            "provider failed",
            status_code=502,
            request_body=trace.request_body,
            response_body=trace.response_body,
        )
    )
    assert detail == {"message": "Provider request failed", "status_code": 502}


def test_sanitizer_keeps_personal_strings_in_recursive_trace_values() -> None:
    sanitized = sanitize_value(
        {
            "summary": "Alice is planning a move to Berlin",
            "nested": ["facts: vegetarian", {"access_token": "token-secret"}],
        }
    )

    assert sanitized["summary"] == "Alice is planning a move to Berlin"
    assert sanitized["nested"][0] == "facts: vegetarian"
    assert sanitized["nested"][1]["access_token"] == "[REDACTED]"
