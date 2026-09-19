from copia.data.agent_log_store import AgentLogStore
from copia.domain.models.agent import Agent
from copia.domain.models.config import AgentConfig, ChatMessage, LLMResponse, ProviderTrace
from copia.domain.models.session import ConversationContext


class SummaryRouter:
    def complete(self, messages, config):
        if config.model == "summary-model":
            openai_key = "s" + "k-summary-secret"
            jwt = "eyJ" + "hbGciOiJIUzI1NiJ9.payload.signature"
            pem = "-----BEGIN " + "PRIVATE KEY-----\nsecret\n-----END " + "PRIVATE KEY-----"
            return LLMResponse(
                content="summary",
                provider=config.provider,
                model=config.model,
                trace=ProviderTrace(
                    status_code=200,
                    request_body={
                        "profile": "Alice",
                        "facts": {"city": "Berlin"},
                        "api_key": openai_key,
                        "authorization": "Bearer summary-secret",
                        "jwt": jwt,
                        "url": "https://user:password@example.test/token/path-secret?key=query-secret",
                    },
                    response_body={
                        "pem": pem,
                    },
                ),
            )
        return LLMResponse(content="answer", provider=config.provider, model=config.model)


def test_successful_summarization_sanitizes_credentials_but_keeps_context() -> None:
    config = AgentConfig.model_validate(
        {
            "name": "test",
            "provider": "openai",
            "model": "main-model",
            "context_management": {
                "recent_exchange_limit": 1,
                "summary_batch_exchange_count": 1,
                "summarizer": {"model": "summary-model"},
            },
        }
    )
    agent = Agent(
        config,
        SummaryRouter(),  # type: ignore[arg-type]
        history=[
            ChatMessage(role="user", content="old"),
            ChatMessage(role="assistant", content="old answer"),
            ChatMessage(role="user", content="recent"),
            ChatMessage(role="assistant", content="recent answer"),
        ],
        context=ConversationContext(),
    )

    agent.ask("new question")

    trace = agent.operation_events[0].trace
    assert trace is not None
    assert trace.request_body["profile"] == "Alice"
    assert trace.request_body["facts"] == {"city": "Berlin"}
    assert trace.request_body["api_key"] == "[REDACTED]"
    assert trace.request_body["authorization"] == "[REDACTED]"
    assert trace.request_body["jwt"] == "[REDACTED]"
    assert "password" not in trace.request_body["url"]
    assert "query-secret" not in trace.request_body["url"]
    assert trace.response_body["pem"] == "[REDACTED]"


def test_finish_turn_sanitizes_legacy_error_surface_without_hiding_context() -> None:
    store = AgentLogStore()
    turn_id = store.start_turn("session", "turn")
    github_token = "ghp" + "_github-secret"
    jwt = "eyJ" + "hbGciOiJIUzI1NiJ9.payload.signature"
    error = (
        "profile=Alice facts=Berlin "
        "api_key=api-secret Authorization: Bearer bearer-secret "
        "Basic basic-secret " + jwt + " sk-error-secret " + github_token + " glpat-gitlab-secret "
        "-----BEGIN PRIVATE KEY-----key-----END PRIVATE KEY----- "
        "https://user:password@example.test/api_key/path-secret?token=query-secret"
    )

    store.finish_turn(turn_id, status="failed", error=error)

    turn = store.get_turn("session", turn_id)
    assert turn is not None
    safe = turn.error or ""
    assert "profile=Alice" in safe
    assert "facts=Berlin" in safe
    for secret in (
        "api-secret",
        "bearer-secret",
        "basic-secret",
        jwt,
        "sk-error-secret",
        github_token,
        "glpat-gitlab-secret",
        "password",
        "path-secret",
        "query-secret",
    ):
        assert secret not in safe


def test_finish_turn_preserves_error_truncation_after_sanitization() -> None:
    store = AgentLogStore()
    turn_id = store.start_turn("session", "turn")
    store.finish_turn(turn_id, error="profile=Alice " + "x" * 600)

    turn = store.get_turn("session", turn_id)
    assert turn is not None
    assert len(turn.error or "") == 500
    assert "profile=Alice" in (turn.error or "")
