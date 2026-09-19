from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import app, router
from copia.data.user_profiles_repository import JsonUserProfilesRepository, UserProfileStorageError
from copia.domain.models.agent_log import AgentLogOperation
from copia.domain.models.config import AgentConfig, LLMResponse
from copia.domain.models.session import ConversationContext
from copia.domain.models.user_profile import UserProfile
from copia.domain.services.context_strategy import context_strategy_for


def profile(name: str = "Personal") -> UserProfile:
    now = datetime.now(UTC)
    return UserProfile(
        id=str(uuid4()),
        name=name,
        language="ru",
        tone="friendly",
        verbosity="balanced",
        response_format=["markdown"],
        constraints=["Keep answers practical"],
        created_at=now,
        updated_at=now,
    )


def test_user_profile_repository_round_trip_and_missing_storage(tmp_path) -> None:
    repository = JsonUserProfilesRepository(tmp_path / "profiles.json")
    assert repository.list() == []
    stored = repository.create(profile())
    assert repository.get(stored.id) == stored
    assert repository.list()[0].name == "Personal"
    assert (tmp_path / "profiles.json").read_text().count('"profiles"') == 1


def test_corrupted_user_profile_storage_is_safe(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text('{"profiles": [{"name": "secret"}]}')
    try:
        JsonUserProfilesRepository(path).list()
    except UserProfileStorageError as error:
        assert str(error) == "User profile storage is unavailable"
    else:
        raise AssertionError("Expected safe storage error")


def test_profile_prompt_contains_only_preferences_and_is_escaped() -> None:
    config = AgentConfig(name="test", provider="openai", model="model", system_prompt="system")
    strategy = context_strategy_for(config, user_profile=profile())
    message = strategy.messages_for_request([], ConversationContext())[0]
    assert message.role == "system"
    assert "<user_profile_preferences>" in message.content
    assert '"id"' not in message.content
    assert "Keep answers practical" in message.content


def test_profile_api_links_session_and_records_operation(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        service, "user_profiles", JsonUserProfilesRepository(tmp_path / "profiles.json")
    )
    monkeypatch.setattr(service, "sessions", service.SessionsRepository(tmp_path / "sessions"))
    created_profile = TestClient(app).post(
        "/user-profiles",
        json={
            "name": "Personal",
            "language": "ru",
            "tone": "friendly",
            "verbosity": "balanced",
            "response_format": ["markdown"],
            "constraints": ["Be practical"],
        },
    )
    assert created_profile.status_code == 201
    client = TestClient(app)
    session = client.post(
        "/sessions",
        json={
            "config": {"name": "Copia", "provider": "openai", "model": "model"},
            "user_profile_id": created_profile.json()["id"],
        },
    )
    assert session.status_code == 201
    monkeypatch.setattr(
        router,
        "complete",
        lambda messages, config: LLMResponse(
            content="ok", provider=config.provider, model=config.model
        ),
    )
    response = client.post(f"/sessions/{session.json()['id']}/messages", json={"content": "Hi"})
    assert response.status_code == 200
    operation = service.agent_log_store.get_turn(
        session.json()["id"], response.json()["agent_log_id"]
    ).operations[0]
    assert isinstance(operation, AgentLogOperation)
    assert operation.status == "completed"
    assert operation.profile_name == "Personal"
