import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from copia import service
from copia.agents.domain.models.agent import Agent
from copia.agents.domain.models.agent_config import AgentConfig
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.providers.data.http_logging import _redacted_body
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.service import app, router
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.conversation_context import ConversationContext
from copia.sessions.domain.services.context_strategy import (
    _estimated_message_tokens,
    context_strategy_for,
)
from copia.user_profiles.data.user_profile_name_conflict_error import UserProfileNameConflictError
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository
from copia.user_profiles.domain.models.user_profile import UserProfile


def profile(name: str) -> UserProfile:
    now = datetime.now(UTC)
    return UserProfile(
        id=str(uuid4()),
        name=name,
        language="en",
        tone="neutral",
        verbosity="balanced",
        response_format=["plain_text"],
        constraints=[],
        created_at=now,
        updated_at=now,
    )


def profile_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "language": "en",
        "tone": "neutral",
        "verbosity": "balanced",
        "response_format": ["plain_text"],
        "constraints": [],
    }


def test_repository_enforces_case_insensitive_name_uniqueness(tmp_path) -> None:
    repository = JsonUserProfilesRepository(tmp_path / "profiles.json")
    first = repository.create(profile("Personal"))

    try:
        repository.create(profile("personal"))
    except UserProfileNameConflictError:
        pass
    else:
        raise AssertionError("Expected a create name conflict")

    second = repository.create(profile("Work"))
    try:
        repository.update(second.id, {"name": "PERSONAL"})
    except UserProfileNameConflictError:
        pass
    else:
        raise AssertionError("Expected an update name conflict")
    assert repository.get(first.id) == first
    assert repository.get(second.id) == second


def test_repository_rejects_duplicate_names_in_existing_storage(tmp_path) -> None:
    first = profile("Personal")
    second = profile("personal")
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps({"profiles": [first.model_dump(mode="json"), second.model_dump(mode="json")]}),
        encoding="utf-8",
    )

    with pytest.raises(UserProfileStorageError, match="unavailable"):
        JsonUserProfilesRepository(path).list()


@pytest.mark.parametrize(
    "context_management",
    [{"enabled": False}, {"strategy": "sliding_window"}, {"strategy": "branching"}],
    ids=["full_transcript", "sliding_window", "branching"],
)
def test_profile_is_passed_to_full_sliding_and_branching_strategies(context_management) -> None:
    config = AgentConfig.model_validate(
        {
            "name": "Copia",
            "provider": "openai",
            "model": "model",
            "context_management": context_management,
        }
    )
    messages = context_strategy_for(config, user_profile=profile("Personal")).messages_for_request(
        [ChatMessage(role="user", content="Hello")], ConversationContext()
    )

    assert "<user_profile_preferences>" in messages[0].content
    assert '"name"' not in messages[0].content


def test_memory_rebuild_preserves_user_profile(tmp_path) -> None:
    class Classifier:
        last_error = None
        last_trace = None
        last_duration_seconds = None

        def classify(self, content, history, working_memory, previous_assistant):
            return []

    config = AgentConfig(name="Copia", provider="openai", model="model")
    user_profile = profile("Personal")
    agent = Agent(
        config,
        object(),  # type: ignore[arg-type]
        session_id="session",
        memory_classifier=Classifier(),  # type: ignore[arg-type]
        working_memory_store=WorkingMemoryRepository(tmp_path),
        user_profile=user_profile,
    )

    agent._classify_memory("Remember this")

    assert agent._strategy._user_profile == user_profile  # type: ignore[attr-defined]


def test_context_window_budget_includes_user_profile_block() -> None:
    config = AgentConfig.model_validate(
        {
            "name": "Copia",
            "provider": "openai",
            "model": "model",
            "generation": {"max_output_tokens": 1},
        }
    )
    memory = LongTermMemoryItem(
        id="memory",
        category="knowledge",
        key="important",
        value="important memory value",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    history = [ChatMessage(role="user", content="Hello")]
    without_profile_strategy = context_strategy_for(config, long_term_memory=[memory])
    without_profile = without_profile_strategy.messages_for_request(history, ConversationContext())
    context_window = (
        sum(_estimated_message_tokens(message.content) for message in without_profile) + 1
    )
    with_profile = context_strategy_for(
        config,
        long_term_memory=[memory],
        context_window=context_window,
        user_profile=profile("Personal"),
    ).messages_for_request(history, ConversationContext())

    assert "important memory value" in without_profile[0].content
    assert "important memory value" not in with_profile[0].content
    assert "<user_profile_preferences>" in with_profile[0].content


def test_profile_crud_maps_conflicts_not_found_and_in_use(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        service, "user_profiles", JsonUserProfilesRepository(tmp_path / "profiles.json")
    )
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    client = TestClient(app)

    created = client.post("/user-profiles", json=profile_payload("Personal"))
    assert created.status_code == 201
    profile_id = created.json()["id"]
    assert (
        client.post("/user-profiles", json=profile_payload("personal")).json()["detail"]["code"]
        == "user_profile_name_conflict"
    )

    second = client.post("/user-profiles", json=profile_payload("Work")).json()
    conflict = client.patch(f"/user-profiles/{second['id']}", json={"name": "PERSONAL"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "user_profile_name_conflict"

    missing = client.patch(f"/user-profiles/{uuid4()}", json={"name": "Missing"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "user_profile_not_found"
    missing_delete = client.delete(f"/user-profiles/{uuid4()}")
    assert missing_delete.status_code == 404
    assert missing_delete.json()["detail"]["code"] == "user_profile_not_found"

    session = client.post(
        "/sessions",
        json={
            "config": {"name": "Copia", "provider": "openai", "model": "model"},
            "user_profile_id": profile_id,
        },
    )
    assert session.status_code == 201
    in_use = client.delete(f"/user-profiles/{profile_id}")
    assert in_use.status_code == 409
    assert in_use.json()["detail"]["code"] == "user_profile_in_use"
    assert client.get("/user-profiles").json()[0]["id"] == profile_id


def test_missing_profile_skips_provider_for_message_and_retry(monkeypatch, tmp_path) -> None:
    repository = JsonUserProfilesRepository(tmp_path / "profiles.json")
    stored = repository.create(profile("Personal"))
    monkeypatch.setattr(service, "user_profiles", repository)
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    client = TestClient(app)
    session = client.post(
        "/sessions",
        json={
            "config": {"name": "Copia", "provider": "openai", "model": "model"},
            "user_profile_id": stored.id,
        },
    )
    assert session.status_code == 201
    repository.delete(stored.id)

    provider_calls = 0

    def complete(messages, config):
        nonlocal provider_calls
        provider_calls += 1
        return LLMResponse(content="unexpected", provider=config.provider, model=config.model)

    monkeypatch.setattr(router, "complete", complete)
    message = client.post(f"/sessions/{session.json()['id']}/messages", json={"content": "Hi"})
    assert message.status_code == 409
    assert message.json()["detail"]["code"] == "user_profile_unavailable"
    assert provider_calls == 0

    retry = client.post(f"/sessions/{session.json()['id']}/summarization/retry")
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "user_profile_unavailable"
    assert provider_calls == 0


def test_profile_load_is_skipped_without_id_and_precedes_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        service, "user_profiles", JsonUserProfilesRepository(tmp_path / "profiles.json")
    )
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    client = TestClient(app)
    session = client.post(
        "/sessions",
        json={"config": {"name": "Copia", "provider": "openai", "model": "model"}},
    )
    assert session.status_code == 201
    calls: list[str] = []

    def complete(messages, config):
        calls.append("provider")
        return LLMResponse(content="ok", provider=config.provider, model=config.model)

    monkeypatch.setattr(router, "complete", complete)
    response = client.post(f"/sessions/{session.json()['id']}/messages", json={"content": "Hi"})
    assert response.status_code == 200
    turn = service.agent_log_store.get_turn(session.json()["id"], response.json()["agent_log_id"])
    assert turn is not None
    assert turn.operations[0].status == "skipped"
    assert calls


def test_corrupt_profile_storage_prevents_provider_request(monkeypatch, tmp_path) -> None:
    profile_path = tmp_path / "profiles.json"
    profile_path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(service, "user_profiles", JsonUserProfilesRepository(profile_path))
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    client = TestClient(app)
    session = client.post(
        "/sessions",
        json={"config": {"name": "Copia", "provider": "openai", "model": "model"}},
    )
    assert session.status_code == 201
    saved = service.sessions.load(session.json()["id"])
    assert saved is not None
    saved.user_profile_id = str(uuid4())
    service.sessions.save(saved)
    provider_calls = 0

    def complete(messages, config):
        nonlocal provider_calls
        provider_calls += 1
        return LLMResponse(content="unexpected", provider=config.provider, model=config.model)

    monkeypatch.setattr(router, "complete", complete)
    response = client.post(f"/sessions/{saved.id}/messages", json={"content": "Hi"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "user_profile_unavailable"
    assert provider_calls == 0


def test_profile_values_are_preserved_while_credentials_are_redacted() -> None:
    config = AgentConfig(name="Copia", provider="openai", model="model")
    agent = Agent(config=config, router=object(), user_profile=profile("Personal"))
    api_key = "s" + "k-secret-value"
    response = LLMResponse(
        content="ok",
        provider="openai",
        model="model",
        trace=ProviderTrace(
            status_code=200,
            request_body={
                "prompt": "Alice prefers concise answers",
                "api_key": api_key,
            },
            response_body={},
        ),
    )
    sanitized = agent._redact_long_term_trace(response)
    assert sanitized.trace is not None
    assert sanitized.trace.request_body["prompt"] == "Alice prefers concise answers"
    assert sanitized.trace.request_body["api_key"] == "[REDACTED]"
    body = _redacted_body(
        f'{{"prompt":"Alice prefers concise answers","api_key":"{api_key}"}}'.encode()
    )
    assert body == b'{"prompt":"Alice prefers concise answers","api_key":"[REDACTED]"}'


def test_two_profiles_produce_different_primary_requests() -> None:
    config = AgentConfig(name="Copia", provider="openai", model="model")
    first = profile("First")
    second = first.model_copy(update={"tone": "formal"})
    request = [ChatMessage(role="user", content="Answer this")]
    first_messages = context_strategy_for(config, user_profile=first).messages_for_request(
        request, ConversationContext()
    )
    second_messages = context_strategy_for(config, user_profile=second).messages_for_request(
        request, ConversationContext()
    )
    assert first_messages != second_messages
