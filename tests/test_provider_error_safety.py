import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from copia import service
from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.service import app
from copia.sessions.domain.models.summarization_event import SummarizationEvent


def test_provider_error_endpoints_never_serialize_provider_payloads(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise ProviderError(
            "Provider request failed",
            status_code=502,
            request_body={"prompt": "private prompt", "apiKey": "request-secret"},
            response_body={"response": "private response", "clientSecret": "response-secret"},
        )

    monkeypatch.setattr(service.router, "models", fail)
    monkeypatch.setattr(service.router, "complete", fail)
    client = TestClient(app)
    responses = (
        client.get("/providers/openai/models"),
        client.post(
            "/completions",
            json={
                "config": {"provider": "openai", "model": "model"},
                "messages": [{"role": "user", "content": "hello"}],
            },
        ),
    )

    for response in responses:
        serialized = json.dumps(response.json())
        assert response.status_code == 502
        assert response.json()["detail"]["status_code"] == 502
        assert "request_body" not in serialized and "response_body" not in serialized
        assert all(secret not in serialized for secret in ("private prompt", "private response"))
        assert "request-secret" not in serialized and "response-secret" not in serialized


def test_session_event_error_redacts_complete_credential_url_and_omits_trace() -> None:
    event = SummarizationEvent(
        id="event",
        status="failed",
        after_message_index=1,
        start_message_index=0,
        message_count=1,
        provider="openai",
        model="model",
        duration_seconds=0,
        error=(
            "https://user:userinfo-secret@provider.test/v1/apiKey/path-secret"
            "?clientSecret=query-secret#accessToken=fragment-secret"
        ),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        trace=ProviderTrace(
            status_code=502,
            request_body={"messages": "private prompt", "apiKey": "request-secret"},
            response_body={"error": "private response", "clientSecret": "response-secret"},
        ),
    )

    response = service._safe_summarization_events([event])[0].model_dump(mode="json")
    serialized = json.dumps(response)

    assert response["trace"] is None
    assert all(secret not in serialized for secret in ("userinfo-secret", "path-secret"))
    assert "query-secret" not in serialized and "fragment-secret" not in serialized
    assert "https://provider.test/v1/apiKey/[REDACTED]" in serialized
