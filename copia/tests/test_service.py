from fastapi.testclient import TestClient

from copia.domain.models.config import LLMResponse
from copia.api.service import agents, app, router


def test_agent_lifecycle_via_api(monkeypatch) -> None:
    def complete(messages, config):
        return LLMResponse(content="reply", provider=config.provider, model=config.model)

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
        return LLMResponse(content="reply", provider=config.provider, model=config.model)

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
