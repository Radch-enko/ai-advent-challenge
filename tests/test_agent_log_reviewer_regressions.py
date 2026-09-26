import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import httpx
from fastapi.testclient import TestClient

from copia import service
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agent_logs.domain.services.agent_log_context import agent_log_turn
from copia.agents.domain.models.agent_config import AgentConfig
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.providers.data.http_logging import (
    install_http_logging,
    record_response,
    record_transport_error,
)
from copia.providers.data.llm import OpenAIProvider
from copia.providers.domain.models.llm_response import LLMResponse
from copia.service import app
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession


def _session_client(monkeypatch, tmp_path, store: AgentLogStore) -> tuple[TestClient, str]:
    root = tmp_path / "sessions"
    monkeypatch.setattr(service, "agent_log_store", store)
    monkeypatch.setattr(service, "sessions", SessionsRepository(root))
    monkeypatch.setattr(service, "working_memory", WorkingMemoryRepository(root))
    monkeypatch.setattr(service, "pending_memory_repository", PendingMemoryRepository(root))
    client = TestClient(app)
    session_id = client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    ).json()["id"]
    return client, session_id


def test_session_initialization_failures_expose_safe_agent_log_ids(monkeypatch, tmp_path) -> None:
    store = AgentLogStore()
    client, session_id = _session_client(monkeypatch, tmp_path, store)

    def fail(*_args, **_kwargs):
        raise OSError("apiKey=raw-initialization-secret")

    failures = (
        lambda patch: patch.setattr(service.sessions, "load_facts", fail),
        lambda patch: patch.setattr(service, "_long_term_memory_for_session", fail),
        lambda patch: patch.setattr(service.working_memory, "load", fail),
        lambda patch: patch.setattr(service.pending_memory_repository, "load", fail),
    )
    for install_failure in failures:
        with monkeypatch.context() as scoped:
            install_failure(scoped)
            response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail["agent_log_id"]
        assert "raw-initialization-secret" not in json.dumps(detail)
        log = client.get(f"/sessions/{session_id}/agent-logs/{detail['agent_log_id']}")
        assert log.status_code == 200
        assert log.json()["status"] == "failed"

    monkeypatch.setattr(service.sessions, "load_facts", fail)
    retry = client.post(f"/sessions/{session_id}/summarization/retry")
    assert retry.status_code == 500
    retry_detail = retry.json()["detail"]
    assert retry_detail["agent_log_id"]
    assert "raw-initialization-secret" not in json.dumps(retry_detail)
    assert (
        client.get(f"/sessions/{session_id}/agent-logs/{retry_detail['agent_log_id']}").json()[
            "status"
        ]
        == "failed"
    )


def test_oversized_provider_response_is_bounded_after_provider_parsing(
    monkeypatch, tmp_path
) -> None:
    store = AgentLogStore(max_body_bytes=128, max_total_body_bytes=1024)
    client, session_id = _session_client(monkeypatch, tmp_path, store)
    large_content = "x" * 4096

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "model": "model",
                "apiKey": "response-secret",
                "choices": [{"message": {"content": large_content}}],
            },
        )

    provider = OpenAIProvider(
        api_key="provider-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        log_store=store,
    )
    turn_id = store.start_turn(session_id)
    with agent_log_turn(session_id, turn_id, provider="openai", model="model"):
        response = provider.complete(
            [ChatMessage(role="user", content="hello")],
            AgentConfig(name="test", provider="openai", model="model"),
        )
    store.finish_turn(turn_id)

    assert response.content == large_content
    detail = client.get(f"/sessions/{session_id}/agent-logs/{turn_id}").json()
    response_body = detail["exchanges"][0]["response_body"]
    assert response_body["size_bytes"] <= store.max_body_bytes
    assert response_body["truncated"] is True
    assert "response-secret" not in json.dumps(detail)


def test_binary_bodies_errors_and_oauth_transport_errors_do_not_leak(monkeypatch, tmp_path) -> None:
    store = AgentLogStore()
    client, session_id = _session_client(monkeypatch, tmp_path, store)
    provider_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, request=request, content=b"\xffapiKey=response-secret"
            )
        )
    )
    install_http_logging(provider_client, store)
    turn_id = store.start_turn(session_id)
    with agent_log_turn(session_id, turn_id, provider="openai", model="model"):
        request = provider_client.build_request(
            "POST", "https://provider.test/chat", content=b"\xffapiKey=request-secret"
        )
        response = provider_client.send(request)
        record_response(store, response)
        error_request = provider_client.build_request("POST", "https://provider.test/error")
        record_transport_error(
            store,
            error_request,
            httpx.ConnectError("apiKey=error-secret", request=error_request),
        )
        oauth_request = provider_client.build_request(
            "POST", "https://provider.test/api/v2/oauth", content=b"auth_key=oauth-secret"
        )
        record_transport_error(
            store,
            oauth_request,
            httpx.ConnectError("auth_key=oauth-secret", request=oauth_request),
        )
    store.finish_turn(turn_id)

    detail = client.get(f"/sessions/{session_id}/agent-logs/{turn_id}").json()
    serialized = json.dumps(detail)
    assert len(detail["exchanges"]) == 2
    assert all(
        secret not in serialized
        for secret in ("request-secret", "response-secret", "error-secret", "oauth-secret")
    )
    request_body = detail["exchanges"][0]["request_body"]
    response_body = detail["exchanges"][0]["response_body"]
    assert request_body["encoding"] == "base64"
    assert response_body["encoding"] == "base64"
    assert base64.b64decode(request_body["content"]).startswith(b"\xffapiKey=[REDACTED]")
    assert base64.b64decode(response_body["content"]).startswith(b"\xffapiKey=[REDACTED]")
    assert "[REDACTED]" in detail["exchanges"][1]["error"]


def test_working_memory_mutation_waits_for_in_flight_session_save(monkeypatch, tmp_path) -> None:
    root = tmp_path / "sessions"
    sessions = SessionsRepository(root)
    working = WorkingMemoryRepository(root)
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "working_memory", working)
    monkeypatch.setattr(service, "pending_memory_repository", PendingMemoryRepository(root))
    monkeypatch.setattr(service, "profile_memory", ProfileMemoryRepository(tmp_path / "memory"))
    now = datetime.now(UTC)
    session = ChatSession(
        id="memory-mutation-session",
        config=AgentConfig(name="test", provider="openai", model="model"),
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)
    working.save(
        session.id,
        [WorkingMemoryItem(id="item", key="goal", value="keep", created_at=now, updated_at=now)],
    )
    provider_started = Event()
    release_provider = Event()

    class Classifier:
        last_error = None

        def classify(self, *_args):
            return []

    monkeypatch.setattr(service, "LLMMemoryClassifier", lambda *_args: Classifier())

    def complete(_messages, config):
        provider_started.set()
        assert release_provider.wait(timeout=5)
        return LLMResponse(content="reply", provider=config.provider, model=config.model)

    monkeypatch.setattr(service.router, "complete", complete)
    client = TestClient(app)
    with ThreadPoolExecutor(max_workers=2) as executor:
        send = executor.submit(
            client.post, f"/sessions/{session.id}/messages", json={"content": "hello"}
        )
        assert provider_started.wait(timeout=5)
        delete = executor.submit(client.delete, f"/sessions/{session.id}/working-memory/item")
        assert not delete.done()
        release_provider.set()
        assert send.result(timeout=5).status_code == 200
        assert delete.result(timeout=5).status_code == 200

    assert working.load(session.id) == []
