from fastapi.testclient import TestClient

from copia.domain.models.config import LLMResponse
from copia.data.sessions_repository import SessionsRepository
from copia.api import service
from copia.api.service import agents, app, router


def test_agent_lifecycle_via_api(monkeypatch) -> None:
    def complete(messages, config):
        return LLMResponse(
            content="reply",
            provider=config.provider,
            model=config.model,
            usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            context_window=400_000,
        )

    monkeypatch.setattr(router, "complete", complete)
    agents.clear()
    client = TestClient(app)
    config = {"name": "api", "provider": "openai", "model": "test-model"}

    created = client.post("/agents", json={"config": config})
    assert created.status_code == 201
    agent_id = created.json()["agent_id"]

    message = client.post(f"/agents/{agent_id}/messages", json={"content": "Hi"})
    assert message.status_code == 200
    assert message.json()["response"]["content"] == "reply"

    assert client.delete(f"/agents/{agent_id}").status_code == 204
    assert client.post(f"/agents/{agent_id}/messages", json={"content": "Hi"}).status_code == 404


def test_create_agent_requires_exactly_one_source() -> None:
    client = TestClient(app)
    assert client.post("/agents", json={}).status_code == 422


def test_direct_completion_does_not_create_agent(monkeypatch) -> None:
    def complete(messages, config):
        return LLMResponse(
            content="reply",
            provider=config.provider,
            model=config.model,
            usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            context_window=400_000,
        )

    monkeypatch.setattr(router, "complete", complete)
    agents.clear()
    client = TestClient(app)
    response = client.post("/completions", json={
        "config": {"provider": "openai", "model": "test-model"},
        "messages": [{"role": "user", "content": "Hi"}],
    })
    assert response.status_code == 200
    assert response.json()["response"]["content"] == "reply"
    assert agents == {}


def test_session_survives_api_restart_and_generates_title(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)

    def complete(messages, config):
        if config.structured_output is not None:
            return LLMResponse(
                content='{"title":"План поездки"}',
                structured_data={"title": "План поездки"},
                provider=config.provider,
                model=config.model,
            )
        return LLMResponse(
            content="reply",
            provider=config.provider,
            model=config.model,
            usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            context_window=400_000,
        )

    monkeypatch.setattr(router, "complete", complete)
    client = TestClient(app)
    created = client.post("/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "test-model"}})
    assert created.status_code == 201
    session_id = created.json()["id"]

    response = client.post(f"/sessions/{session_id}/messages", json={"content": "Помоги спланировать поездку"})
    assert response.status_code == 200

    restarted_repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", restarted_repository)
    restored = client.get(f"/sessions/{session_id}")
    assert [message["content"] for message in restored.json()["messages"]] == ["Помоги спланировать поездку", "reply"]
    assert restored.json()["messages"][1]["usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 3,
        "total_tokens": 15,
    }
    assert restored.json()["messages"][1]["context_window"] == 400_000
    assert restored.json()["title"] == "План поездки"
    assert client.get("/sessions").json()[0]["id"] == session_id


def test_regular_session_accepts_new_config_and_can_be_deleted(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    seen_models = []

    def complete(messages, config):
        seen_models.append(config.model)
        return LLMResponse(content="reply", provider=config.provider, model=config.model)

    monkeypatch.setattr(router, "complete", complete)
    client = TestClient(app)
    created = client.post("/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "first-model"}})
    session_id = created.json()["id"]

    response = client.post(f"/sessions/{session_id}/messages", json={
        "content": "Hi",
        "config": {"name": "Copia", "provider": "openai", "model": "second-model"},
    })

    assert response.status_code == 200
    assert seen_models[0] == "second-model"
    assert client.delete(f"/sessions/{session_id}").status_code == 204
    assert client.get(f"/sessions/{session_id}").status_code == 404
