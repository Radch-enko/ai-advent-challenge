import json

import httpx
from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import app
from copia.data.agent_log_store import AgentLogStore
from copia.data.providers.http_logging import install_http_logging, record_response
from copia.data.sessions_repository import SessionsRepository
from copia.domain.services.agent_log_context import agent_log_turn


def test_credential_query_values_are_redacted_before_agent_log_api_serialization(
    monkeypatch, tmp_path
) -> None:
    store = AgentLogStore()
    monkeypatch.setattr(service, "agent_log_store", store)
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    session_client = TestClient(app)
    session_id = session_client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    ).json()["id"]
    turn_id = store.start_turn(session_id)

    provider_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    )
    install_http_logging(provider_client, store)
    secrets = ("client-secret-value", "id-token-value", "auth-key-value")
    with agent_log_turn(session_id, turn_id, provider="openai", model="model"):
        response = provider_client.get(
            "https://provider.test/chat?client_secret=client-secret-value"
            "&ID-TOKEN=id-token-value&Auth_Key=auth-key-value"
        )
        record_response(store, response)
    store.finish_turn(turn_id)

    stored = store.get_turn(session_id, turn_id)
    assert stored is not None
    assert "client_secret=[REDACTED]" in stored.exchanges[0].url
    assert "ID-TOKEN=[REDACTED]" in stored.exchanges[0].url
    assert "Auth_Key=[REDACTED]" in stored.exchanges[0].url
    assert all(secret not in stored.exchanges[0].url for secret in secrets)

    detail = session_client.get(f"/sessions/{session_id}/agent-logs/{turn_id}")
    assert detail.status_code == 200
    assert all(secret not in json.dumps(detail.json()) for secret in secrets)
