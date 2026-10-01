from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from conversation_test_client import ConversationTestClient

from copia import service
from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.conversations.application.conversation_store import ConversationStore
from copia.document_indexing.domain.errors import DocumentRetrievalError
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.models.task_status import TaskStatus


def setup_runtime(monkeypatch, tmp_path: Path) -> SessionsRepository:
    sessions = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "conversation_store", ConversationStore())
    return sessions


def create_session(client: ConversationTestClient, **settings: bool) -> dict:
    return client.post(
        "/sessions",
        json={
            "config": {"name": "Copia", "provider": "openai", "model": "test-model"},
            **settings,
        },
    ).json()


def test_rag_mode_defaults_off_and_persists_across_session_reload(
    monkeypatch, tmp_path: Path
) -> None:
    sessions = setup_runtime(monkeypatch, tmp_path)
    client = ConversationTestClient(service.app)

    created = create_session(client)
    assert created["rag_enabled"] is False

    updated = client.patch(f"/sessions/{created['id']}/rag-mode", json={"enabled": True})
    assert updated.status_code == 200
    assert updated.json()["rag_enabled"] is True
    assert client.get(f"/sessions/{created['id']}").json()["rag_enabled"] is True
    assert sessions.load(created["id"]).rag_enabled is True

    legacy = ChatSession.model_validate_json(
        json.dumps(
            {
                "id": "legacy",
                "config": {"name": "Copia", "provider": "openai", "model": "test"},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
    )
    assert legacy.rag_enabled is False


def test_rag_mode_cannot_change_while_task_is_active(monkeypatch, tmp_path: Path) -> None:
    sessions = setup_runtime(monkeypatch, tmp_path)
    client = ConversationTestClient(service.app)
    created = create_session(client, rag_enabled=True, task_mode_enabled=True)
    session = sessions.load(created["id"])
    now = datetime.now(UTC)
    session.task = TaskState(
        id="task-active",
        original_instruction="Work with the local corpus",
        status=TaskStatus.RUNNING,
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)

    response = client.patch(f"/sessions/{created['id']}/rag-mode", json={"enabled": False})

    assert response.status_code == 409
    assert sessions.load(created["id"]).rag_enabled is True


def test_chat_retrieves_only_when_enabled_and_persists_used_source(
    monkeypatch, tmp_path: Path
) -> None:
    sessions = setup_runtime(monkeypatch, tmp_path)
    retrieved_questions: list[str] = []
    retrieved_chunk = RetrievedChunk(
        text="The local document states that retrieval uses one best chunk.",
        source=KnowledgeSource(
            chunk_id="guide-3", source="guide.md", title="Guide", section="Retrieval"
        ),
    )

    def retrieve(question: str) -> RetrievedChunk:
        retrieved_questions.append(question)
        return retrieved_chunk

    monkeypatch.setattr(service.document_indexing_composition.retriever, "retrieve", retrieve)
    captured_messages = []

    def complete(messages, config, tools=None):
        captured_messages.append(messages)
        return LLMResponse(
            content="The retrieved guide says to select one best chunk.",
            provider=ProviderName.OPENAI,
            model=config.model,
        )

    monkeypatch.setattr(service.router, "complete", complete)
    client = ConversationTestClient(service.app)

    session = create_session(client)
    saved_session = sessions.load(session["id"])
    saved_session.title = "RAG test"
    sessions.save(saved_session)
    no_rag = client.post(
        f"/sessions/{session['id']}/messages", json={"content": "Question without RAG"}
    )
    assert no_rag.status_code == 200
    assert no_rag.json()["sources"] == []
    assert retrieved_questions == []

    enabled = client.patch(f"/sessions/{session['id']}/rag-mode", json={"enabled": True})
    assert enabled.status_code == 200
    with_rag = client.post(
        f"/sessions/{session['id']}/messages", json={"content": "Question with RAG"}
    )

    assert with_rag.status_code == 200
    assert retrieved_questions == ["Question with RAG"]
    assert "The local document states" in captured_messages[-1][0].content
    assert with_rag.json()["response"]["content"].startswith("The retrieved guide")
    assert with_rag.json()["sources"] == [
        {"chunk_id": "guide-3", "source": "guide.md", "title": "Guide", "section": "Retrieval"}
    ]
    stored = client.get(f"/sessions/{session['id']}").json()
    assert stored["messages"][-1]["sources"][0]["chunk_id"] == "guide-3"


def test_missing_index_error_is_visible_and_does_not_call_llm(monkeypatch, tmp_path: Path) -> None:
    setup_runtime(monkeypatch, tmp_path)
    llm_calls = 0

    def retrieve(_question: str) -> RetrievedChunk:
        raise DocumentRetrievalError(
            "RAG is enabled, but no completed document index is available."
        )

    def complete(messages, config, tools=None):
        nonlocal llm_calls
        llm_calls += 1
        return LLMResponse(content="unexpected", provider=ProviderName.OPENAI, model=config.model)

    monkeypatch.setattr(service.document_indexing_composition.retriever, "retrieve", retrieve)
    monkeypatch.setattr(service.router, "complete", complete)
    client = ConversationTestClient(service.app)
    session = create_session(client, rag_enabled=True)
    saved_session = service.sessions.load(session["id"])
    saved_session.title = "RAG error test"
    service.sessions.save(saved_session)

    response = client.post(f"/sessions/{session['id']}/messages", json={"content": "Question"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "rag_unavailable"
    assert llm_calls == 0
    assert service.sessions.load(session["id"]).messages == []
