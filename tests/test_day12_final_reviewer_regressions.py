import json
from datetime import UTC, datetime
from uuid import uuid4

from conversation_test_client import ConversationTestClient as TestClient

from copia import service
from copia.service import app
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository


def test_escaped_profile_size_fails_before_provider(monkeypatch, tmp_path) -> None:
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
