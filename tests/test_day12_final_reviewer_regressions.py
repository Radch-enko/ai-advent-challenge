import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from copia import service
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.providers.data.http_logging import _capture_body
from copia.service import app
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository


def test_credential_redaction_precedes_body_truncation() -> None:
    class Store:
        max_body_bytes = 64

    secret = "s" + "k-profile-token-that-must-not-survive-truncation"
    body = (
        b'{"prompt":"Alice prefers concise answers","api_key":"'
        + secret.encode()
        + b'","tail":"ordinary-'
        + b"x" * 100
        + b'"}'
    )

    captured, truncated = _capture_body(Store(), body)  # type: ignore[arg-type]

    assert truncated is True
    assert secret.encode() not in (captured or b"")
    assert b"Alice prefers concise answers" in (captured or b"")
    assert b"[REDACTED]" in (captured or b"")


def test_escaped_profile_size_fails_before_completed_operation_or_provider(
    monkeypatch, tmp_path
) -> None:
    profile_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    oversized = {
        "profiles": [
            {
                "id": profile_id,
                "name": "Unsafe",
                "language": "en",
                "tone": "neutral",
                "verbosity": "balanced",
                "response_format": ["plain_text"],
                "constraints": ["<" * 150 for _ in range(8)],
                "created_at": now,
                "updated_at": now,
            }
        ]
    }
    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(json.dumps(oversized), encoding="utf-8")
    monkeypatch.setattr(service, "user_profiles", JsonUserProfilesRepository(profile_path))
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    store = AgentLogStore()
    monkeypatch.setattr(service, "agent_log_store", store)
    client = TestClient(app)

    session = client.post(
        "/sessions",
        json={
            "config": {"name": "Copia", "provider": "openai", "model": "model"},
        },
    )
    assert session.status_code == 201
    saved = service.sessions.load(session.json()["id"])
    assert saved is not None
    saved.user_profile_id = profile_id
    service.sessions.save(saved)
    provider_calls = 0

    def complete(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(service.router, "complete", complete)
    response = client.post(f"/sessions/{session.json()['id']}/messages", json={"content": "Hi"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "user_profile_unavailable"
    assert provider_calls == 0
    turn = store.get_turn(session.json()["id"], response.json()["detail"]["agent_log_id"])
    assert turn is not None
    assert turn.status == "failed"
    assert turn.operations[0].status == "failed"
    assert turn.operations[0].applied is False
