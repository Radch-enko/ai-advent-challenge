import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from copia import service
from copia.agent_logs.data.agent_log_repository import JsonAgentLogRepository
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agents.domain.models.agent import Agent
from copia.agents.domain.models.agent_config import AgentConfig
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.invariants.domain.models.invariant import Invariant
from copia.providers.domain.models.llm_response import LLMResponse
from copia.service import app, router
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession


def invariant(
    name: str = "Selected architecture", text: str = "Backend remains Python and FastAPI"
) -> Invariant:
    now = datetime.now(UTC)
    return Invariant(
        id="invariant-id",
        name=name,
        text=text,
        created_at=now,
        updated_at=now,
    )


def test_invariants_repository_is_separate_from_session_transcript(tmp_path) -> None:
    repository = InvariantsRepository(tmp_path / "invariants.json")

    repository.save([invariant()])

    assert repository.load()[0].text == "Backend remains Python and FastAPI"
    assert (tmp_path / "invariants.json").is_file()
    assert not (tmp_path / "session.json").exists()


def test_invariants_repository_migrates_legacy_session_files(tmp_path) -> None:
    sessions = tmp_path / "sessions"
    legacy_path = sessions / "session-id" / "invariants.json"
    legacy_item = invariant().model_dump(mode="json")
    legacy_item.pop("name")
    legacy_item["category"] = "business_rule"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(json.dumps({"items": [legacy_item]}), encoding="utf-8")

    repository = InvariantsRepository(tmp_path / "invariants.json", legacy_sessions_root=sessions)

    assert repository.load()[0].name == "Business Rule"
    assert (tmp_path / "invariants.json").is_file()


def test_agent_includes_invariants_in_the_provider_context() -> None:
    requests: list[list[ChatMessage]] = []

    class Router:
        def complete(self, messages, config):
            requests.append(messages)
            return LLMResponse(
                content="I cannot violate the invariant",
                provider=config.provider,
                model=config.model,
            )

    agent = Agent(
        AgentConfig(
            name="Copia",
            provider="openai",
            model="test-model",
            system_prompt="You are Copia.",
        ),
        Router(),  # type: ignore[arg-type]
        invariants=[invariant(text="Do not add dependencies without an explicit decision")],
    )

    response = agent.ask("Add a new dependency without discussing it")

    assert response.content == "I cannot violate the invariant"
    system = requests[-1][0].content
    assert "<invariants>" in system
    assert "Do not add dependencies without an explicit decision" in system
    assert "do not propose a violating solution" in system
    assert requests[-1][-1].content == "Add a new dependency without discussing it"


def test_agent_primary_request_restores_invariants_after_strategy_projection(monkeypatch) -> None:
    requests: list[list[ChatMessage]] = []

    class Router:
        def complete(self, messages, config):
            requests.append(messages)
            return LLMResponse(content="reply", provider=config.provider, model=config.model)

    agent = Agent(
        AgentConfig(
            name="Copia",
            provider="openai",
            model="test-model",
            system_prompt="You are Copia.",
        ),
        Router(),  # type: ignore[arg-type]
        invariants=[invariant(text="Never schedule work on weekends")],
    )
    monkeypatch.setattr(
        agent._strategy,
        "messages_for_request",
        lambda history, context: [
            ChatMessage(role="system", content="You are Copia."),
            *history,
        ],
    )

    agent.ask("Suggest a plan")

    assert "<invariants>" in requests[-1][0].content
    assert "Never schedule work on weekends" in requests[-1][0].content


def test_session_invariant_crud_and_request_inclusion(monkeypatch, tmp_path) -> None:
    sessions = SessionsRepository(tmp_path / "sessions")
    invariants = InvariantsRepository(tmp_path / "invariants.json")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "invariants_repository", invariants)
    monkeypatch.setattr(service, "working_memory", WorkingMemoryRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service,
        "pending_memory_repository",
        PendingMemoryRepository(tmp_path / "sessions"),
    )
    monkeypatch.setattr(
        service,
        "agent_log_store",
        AgentLogStore(repository=JsonAgentLogRepository(tmp_path / "sessions")),
    )
    requests: list[list[ChatMessage]] = []

    def complete(messages, config):
        requests.append(messages)
        return LLMResponse(content="reply", provider=config.provider, model=config.model)

    monkeypatch.setattr(router, "complete", complete)
    client = TestClient(app)
    created = client.post(
        "/sessions",
        json={"config": {"name": "Copia", "provider": "openai", "model": "test-model"}},
    )
    session_id = created.json()["id"]

    created_invariant = client.post(
        "/invariants",
        json={"name": "API architecture", "text": "Keep the API layer in FastAPI"},
    )
    assert created_invariant.status_code == 201
    assert created_invariant.json()["name"] == "API architecture"
    item_id = created_invariant.json()["id"]
    assert client.get("/invariants").json()[0]["text"] == ("Keep the API layer in FastAPI")

    updated = client.patch(
        f"/invariants/{item_id}",
        json={"text": "Keep the API layer in Python and FastAPI"},
    )
    assert updated.status_code == 200

    sent = client.post(f"/sessions/{session_id}/messages", json={"content": "Change the API"})
    assert sent.status_code == 200
    assert "Keep the API layer in Python and FastAPI" in requests[-1][0].content

    other_session = client.post(
        "/sessions",
        json={"config": {"name": "Copia", "provider": "openai", "model": "test-model"}},
    )
    assert client.get(f"/sessions/{other_session.json()['id']}/invariants").json()[0]["name"] == (
        "API architecture"
    )

    completion = client.post(
        "/completions",
        json={
            "config": {
                "provider": "openai",
                "model": "test-model",
                "system_prompt": "You are Copia.",
            },
            "messages": [{"role": "user", "content": "Change the API"}],
        },
    )
    assert completion.status_code == 200
    assert "Keep the API layer in Python and FastAPI" in requests[-1][0].content

    service.agents.clear()
    created_agent = client.post(
        "/agents",
        json={"config": {"name": "Copia", "provider": "openai", "model": "test-model"}},
    )
    direct_agent = client.post(
        f"/agents/{created_agent.json()['agent_id']}/messages",
        json={"content": "Change the API"},
    )
    assert direct_agent.status_code == 200
    assert "Keep the API layer in Python and FastAPI" in requests[-1][0].content

    assert client.delete(f"/invariants/{item_id}").status_code == 204
    assert client.get("/invariants").json() == []


def test_task_mode_system_context_includes_global_invariants(monkeypatch, tmp_path) -> None:
    repository = InvariantsRepository(tmp_path / "invariants.json")
    repository.save([invariant(text="Task mode must keep the selected architecture")])
    monkeypatch.setattr(service, "invariants_repository", repository)
    session = ChatSession(
        id="session-id",
        config=AgentConfig(name="Copia", provider="openai", model="test-model"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    messages = service._task_system_messages(session, "You are the task planner.")

    assert "Task mode must keep the selected architecture" in messages[0].content
    assert messages[-1].content == "You are the task planner."
