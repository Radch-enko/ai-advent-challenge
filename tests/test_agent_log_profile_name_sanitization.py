import json

import pytest
from fastapi.testclient import TestClient

from copia import service
from copia.agent_logs.data.agent_log_repository import JsonAgentLogRepository
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.providers.domain.models.llm_response import LLMResponse
from copia.service import app
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository


@pytest.mark.parametrize(
    ("profile_name", "expected_name"),
    [("api_key=secret", "api_key=[REDACTED]"), ("Personal", "Personal")],
)
def test_agent_log_profile_name_is_sanitized_in_memory_and_after_restart(
    monkeypatch, tmp_path, profile_name, expected_name
) -> None:
    sessions_root = tmp_path / "sessions"
    monkeypatch.setattr(service, "sessions", SessionsRepository(sessions_root))
    monkeypatch.setattr(
        service, "user_profiles", JsonUserProfilesRepository(tmp_path / "profiles.json")
    )
    first_store = AgentLogStore(repository=JsonAgentLogRepository(sessions_root))
    monkeypatch.setattr(service, "agent_log_store", first_store)
    monkeypatch.setattr(
        service.router,
        "complete",
        lambda messages, config: LLMResponse(
            content="ok", provider=config.provider, model=config.model
        ),
    )
    client = TestClient(app)

    created_profile = client.post(
        "/user-profiles",
        json={
            "name": profile_name,
            "language": "en",
            "tone": "neutral",
            "verbosity": "concise",
            "response_format": ["plain_text"],
        },
    )
    assert created_profile.status_code == 201
    session = client.post(
        "/sessions",
        json={
            "config": {"name": "Copia", "provider": "openai", "model": "model"},
            "user_profile_id": created_profile.json()["id"],
        },
    )
    assert session.status_code == 201

    response = client.post(f"/sessions/{session.json()['id']}/messages", json={"content": "Hi"})
    assert response.status_code == 200
    log_id = response.json()["agent_log_id"]
    session_id = session.json()["id"]

    in_memory = first_store.get_turn(session_id, log_id)
    assert in_memory is not None
    assert in_memory.operations[0].profile_name == expected_name

    monkeypatch.setattr(
        service, "agent_log_store", AgentLogStore(repository=JsonAgentLogRepository(sessions_root))
    )
    persisted = client.get(f"/sessions/{session_id}/agent-logs/{log_id}")
    assert persisted.status_code == 200
    assert persisted.json()["operations"][0]["profile_name"] == expected_name
    if profile_name == "api_key=secret":
        assert "secret" not in json.dumps(persisted.json())
