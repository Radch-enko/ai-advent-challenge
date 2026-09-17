import json
from datetime import UTC, datetime
from threading import Event, Thread

import httpx
from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import app
from copia.data.agent_log_store import AgentLogStore
from copia.data.providers.http_logging import _redact_url, install_http_logging, record_response
from copia.data.sessions_repository import SessionsRepository
from copia.domain.models.session import ChatSession, SummarizationEvent
from copia.domain.services.agent_log_context import agent_log_turn


def test_credential_userinfo_path_query_and_body_values_are_redacted_in_storage_and_api(
    monkeypatch, tmp_path
) -> None:
    store = AgentLogStore()
    monkeypatch.setattr(service, "agent_log_store", store)
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    client = TestClient(app)
    session_id = client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    ).json()["id"]
    turn_id = store.start_turn(session_id)
    sentinel_values = (
        "userinfo-secret",
        "path-api-secret",
        "path-token-secret",
        "query-cookie-secret",
        "query-cookie-secret-2",
        "body-api-secret",
        "body-client-secret",
        "body-access-secret",
        "body-cookie-secret",
        "body-cookie-secret-2",
    )
    url = (
        "https://user:userinfo-secret@provider.test/v1/apiKey/path-api-secret/"
        "accessToken/path-token-secret/chat?cookie=query-cookie-secret&set-cookie=query-cookie-secret-2"
    )
    redacted_url = _redact_url(url)
    assert all(value not in redacted_url for value in sentinel_values)
    assert "provider.test/v1/apiKey/[REDACTED]/accessToken/[REDACTED]/chat" in redacted_url

    provider_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"ok": True})
        )
    )
    install_http_logging(provider_client, store)
    body = json.dumps(
        {
            "apiKey": "body-api-secret",
            "clientSecret": "body-client-secret",
            "accessToken": "body-access-secret",
            "cookie": "body-cookie-secret",
            "set-cookie": "body-cookie-secret-2",
            "prompt": "ordinary prompt remains present",
        }
    ).encode()
    with agent_log_turn(session_id, turn_id, provider="openai", model="model"):
        request = provider_client.build_request("POST", url, content=body)
        response = provider_client.send(request)
        record_response(store, response)
    store.finish_turn(turn_id)

    stored = store.get_turn(session_id, turn_id)
    assert stored is not None
    stored_text = json.dumps(stored.model_dump(mode="json"), default=str)
    assert all(value not in stored_text for value in sentinel_values)
    assert b"ordinary prompt remains present" in (stored.exchanges[0].request_body or b"")

    detail = client.get(f"/sessions/{session_id}/agent-logs/{turn_id}")
    assert detail.status_code == 200
    detail_text = json.dumps(detail.json())
    assert all(value not in detail_text for value in sentinel_values)
    assert "ordinary prompt remains present" in detail_text


def test_url_redaction_removes_all_userinfo_and_fragment_credentials() -> None:
    url = "https://secret@provider.test/chat?cookie=query-secret#accessToken=fragment-secret"
    redacted = _redact_url(url)
    assert "@" not in redacted
    assert "secret" not in redacted
    assert "query-secret" not in redacted
    assert "fragment-secret" not in redacted
    assert redacted == "https://provider.test/chat?cookie=[REDACTED]#accessToken=[REDACTED]"


def test_session_load_and_agent_construction_failures_return_safe_log_ids(
    monkeypatch, tmp_path
) -> None:
    store = AgentLogStore()
    monkeypatch.setattr(service, "agent_log_store", store)
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    client = TestClient(app)
    session_id = client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    ).json()["id"]

    original_load = repository.load

    def failing_load(value: str):
        if value == session_id:
            raise OSError("apiKey=load-secret")
        return original_load(value)

    monkeypatch.setattr(repository, "load", failing_load)
    failed_load = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
    assert failed_load.status_code == 500
    load_detail = failed_load.json()["detail"]
    assert load_detail["agent_log_id"]
    assert "load-secret" not in json.dumps(load_detail)

    monkeypatch.setattr(repository, "load", original_load)

    class FailingAgent:
        def __init__(self, **_kwargs):
            raise ValueError("clientSecret=agent-secret")

    monkeypatch.setattr(service, "Agent", FailingAgent)
    failed_agent = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
    assert failed_agent.status_code == 500
    agent_detail = failed_agent.json()["detail"]
    assert agent_detail["agent_log_id"]
    assert "agent-secret" not in json.dumps(agent_detail)
    assert (
        client.get(f"/sessions/{session_id}/agent-logs/{agent_detail['agent_log_id']}").json()[
            "status"
        ]
        == "failed"
    )


def test_provider_error_endpoints_never_serialize_provider_payloads(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise service.ProviderError(
            "provider payload apiKey=error-secret",
            status_code=502,
            request_body={"apiKey": "request-secret"},
            response_body={"clientSecret": "response-secret"},
        )

    monkeypatch.setattr(service.router, "models", fail)
    monkeypatch.setattr(service.router, "complete", fail)
    client = TestClient(app)

    models = client.get("/providers/openai/models")
    completion = client.post(
        "/completions",
        json={
            "config": {"provider": "openai", "model": "model"},
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    for response in (models, completion):
        assert response.status_code == 502
        payload = json.dumps(response.json())
        assert all(
            secret not in payload
            for secret in ("error-secret", "request-secret", "response-secret")
        )
        assert "request_body" in payload
        assert "response_body" in payload


def test_session_event_error_redacts_complete_credential_url() -> None:
    secret_values = ("user", "userinfo-secret", "path-secret", "query-secret", "fragment-secret")
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
    )

    serialized = json.dumps(service._safe_summarization_events([event])[0].model_dump(mode="json"))
    assert all(secret not in serialized for secret in secret_values)
    assert "https://provider.test/v1/apiKey/[REDACTED]" in serialized
    assert "clientSecret=[REDACTED]" in serialized
    assert "accessToken=[REDACTED]" in serialized


def test_session_lock_cleanup_waits_for_blocked_users(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    now = datetime.now(UTC)
    session = ChatSession(
        id="lock-cleanup-session",
        config={"name": "test", "provider": "openai", "model": "model"},
        created_at=now,
        updated_at=now,
    )
    repository.save(session)
    state = service._session_message_lock(session.id)
    state.lock.acquire()
    waiter_started = Event()
    waiter_finished = Event()

    def waiter() -> None:
        waiter_state = service._session_message_lock(session.id)
        waiter_started.set()
        waiter_state.lock.acquire()
        waiter_state.lock.release()
        service._release_session_message_lock(waiter_state)
        waiter_finished.set()

    waiter_thread = Thread(target=waiter)
    waiter_thread.start()
    assert waiter_started.wait(timeout=1)
    delete_thread = Thread(target=lambda: service.delete_session(session.id))
    delete_thread.start()
    state.lock.release()
    service._release_session_message_lock(state)
    delete_thread.join(timeout=2)
    waiter_thread.join(timeout=2)

    assert waiter_finished.is_set()
    assert session.id not in service.session_message_locks
