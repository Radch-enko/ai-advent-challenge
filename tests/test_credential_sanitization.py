from copia.api.service import _safe_trace, provider_error_detail
from copia.data.providers.http_logging import _capture_body, _redact_headers
from copia.data.providers.llm import ProviderError
from copia.domain.models.agent import Agent
from copia.domain.models.config import AgentConfig, LLMResponse, ProviderTrace
from copia.domain.services.credential_sanitizer import sanitize_value


def test_http_body_preserves_personal_context_and_redacts_credentials_before_truncation() -> None:
    class Store:
        max_body_bytes = 180

    personal = "profile=Alice facts=vegetarian working=finish the report"
    openai_token = "s" + "k-test-token-12345"
    github_token = "ghp" + "_github-secret-12345"
    gitlab_token = "glpat" + "-gitlab-secret-12345"
    jwt = "eyJ" + "hbGciOiJIUzI1NiJ9.payload.signature"
    pem_begin = "-----BEGIN " + "PRIVATE KEY-----"
    pem_end = "-----END " + "PRIVATE KEY-----"
    payload = (
        f'{{"prompt":"{personal}","api_key":"{openai_token}","access_token":"access-secret",'
        '"authorization":"Bearer bearer-secret",'
        f'"jwt":"{jwt}","pem":"{pem_begin}\nsecret\n{pem_end}",'
        f'"github":"{github_token}","gitlab":"{gitlab_token}",'
        '"url":"https://user:password@provider.test/chat?access_token=url-secret",'
        '"tail":"' + "x" * 500 + '"}'
    ).encode()

    captured, truncated = _capture_body(Store(), payload)  # type: ignore[arg-type]

    text = (captured or b"").decode()
    assert truncated is True
    assert personal in text
    assert openai_token not in text
    assert "access-secret" not in text
    assert "bearer-secret" not in text
    assert jwt not in text
    assert github_token not in text
    assert gitlab_token not in text
    assert "PRIVATE KEY-----" not in text
    assert "password@" not in text
    assert "url-secret" not in text


def test_sensitive_headers_include_authenticate_challenges() -> None:
    import httpx

    headers = _redact_headers(
        httpx.Headers(
            {
                "WWW-Authenticate": "Bearer challenge-secret",
                "Proxy-Authenticate": "Basic proxy-secret",
                "X-Personal-Context": "Alice prefers concise answers",
            }
        )
    )

    assert headers["www-authenticate"] == "[REDACTED]"
    assert headers["proxy-authenticate"] == "[REDACTED]"
    assert headers["x-personal-context"] == "Alice prefers concise answers"


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

    safe = _safe_trace(trace)
    assert safe is not None
    assert safe.request_body["profile"] == "Alice"
    assert safe.request_body["api_key"] == "[REDACTED]"
    detail = provider_error_detail(
        ProviderError(
            "provider failed",
            status_code=502,
            request_body=trace.request_body,
            response_body=trace.response_body,
        )
    )
    assert detail["provider_trace"]["request_body"]["profile"] == "Alice"  # type: ignore[index]


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
