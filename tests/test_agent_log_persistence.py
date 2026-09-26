from datetime import UTC, datetime

from fastapi.testclient import TestClient

from copia import service
from copia.agent_logs.data.agent_log_repository import JsonAgentLogRepository
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agent_logs.domain.models.agent_log_exchange import AgentLogExchange
from copia.service import app
from copia.sessions.data.sessions_repository import SessionsRepository


def _exchange(turn_id: str, session_id: str) -> AgentLogExchange:
    return AgentLogExchange(
        id="exchange-1",
        agent_turn_id=turn_id,
        session_id=session_id,
        operation="primary",
        provider="openai",
        model="model",
        method="POST",
        url="https://provider.test/chat",
        request_headers={"authorization": "[REDACTED]"},
        request_body=b"\xff\x00request",
        status_code=200,
        response_headers={},
        response_body=b"\x80response",
        duration_seconds=0.25,
        created_at=datetime.now(UTC),
    )


def test_json_agent_log_repository_round_trips_binary_bodies(tmp_path) -> None:
    repository = JsonAgentLogRepository(tmp_path / "sessions")
    store = AgentLogStore(repository=repository)
    turn_id = store.start_turn("session", "turn")
    assert store.append(_exchange(turn_id, "session"))
    store.finish_turn(turn_id, provider="openai", model="model", usage={"total_tokens": 3})

    restarted_store = AgentLogStore(repository=JsonAgentLogRepository(tmp_path / "sessions"))
    turn = restarted_store.get_turn("session", turn_id)

    assert turn is not None
    assert turn.status == "completed"
    assert turn.duration_seconds >= 0
    assert turn.usage == {"total_tokens": 3}
    assert turn.exchanges[0].request_body == b"\xff\x00request"
    assert turn.exchanges[0].response_body == b"\x80response"


def test_agent_log_api_reads_persisted_turn_after_store_restart(monkeypatch, tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    monkeypatch.setattr(service, "sessions", SessionsRepository(sessions_root))
    first_store = AgentLogStore(repository=JsonAgentLogRepository(sessions_root))
    monkeypatch.setattr(service, "agent_log_store", first_store)
    client = TestClient(app)

    session_id = client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    ).json()["id"]
    turn_id = first_store.start_turn(session_id, "turn")
    first_store.append(_exchange(turn_id, session_id))
    first_store.finish_turn(turn_id, provider="openai", model="model")

    monkeypatch.setattr(
        service,
        "agent_log_store",
        AgentLogStore(repository=JsonAgentLogRepository(sessions_root)),
    )
    detail = client.get(f"/sessions/{session_id}/agent-logs/{turn_id}")

    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    assert detail.json()["exchanges"][0]["request_body"]["encoding"] == "base64"

    assert client.delete(f"/sessions/{session_id}").status_code == 204
    assert client.get(f"/sessions/{session_id}/agent-logs/{turn_id}").status_code == 404
