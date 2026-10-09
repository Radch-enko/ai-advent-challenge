from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from conversation_test_client import ConversationTestClient

from copia import service
from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.conversations.application.conversation_store import ConversationStore
from copia.document_indexing.domain.errors import DocumentRetrievalError
from copia.document_indexing.domain.models.rag_retrieval_result import RagRetrievalResult
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.models.context_management_config import ContextManagementConfig
from copia.sessions.domain.models.conversation_context import ConversationContext
from copia.sessions.domain.models.summarization_event import SummarizationEvent
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
        if config.structured_output is None:
            return LLMResponse(
                content="A plain answer without retrieval.",
                provider=ProviderName.OPENAI,
                model=config.model,
            )
        answer = 'The guide says retrieval uses one best chunk: "retrieval uses one best chunk".'
        data = {
            "answer": answer,
            "citations": [{"chunk_id": "guide-3", "quote": "retrieval uses one best chunk"}],
        }
        return LLMResponse(
            content=json.dumps(data),
            provider=ProviderName.OPENAI,
            model=config.model,
            structured_data=data,
        )

    monkeypatch.setattr(service.router, "complete", complete)
    client = ConversationTestClient(service.app)

    session = create_session(client)
    saved_session = sessions.load(session["id"])
    saved_session.title = "RAG test"
    saved_session.rag_settings = saved_session.rag_settings.model_copy(
        update={"query_rewrite_enabled": False}
    )
    sessions.save(saved_session)
    no_rag = client.post(
        f"/sessions/{session['id']}/messages", json={"content": "Question without RAG"}
    )
    assert no_rag.status_code == 200
    assert no_rag.json()["sources"] == []
    assert no_rag.json()["rag_enabled"] is False
    assert retrieved_questions == []

    enabled = client.patch(f"/sessions/{session['id']}/rag-mode", json={"enabled": True})
    assert enabled.status_code == 200
    with_rag = client.post(
        f"/sessions/{session['id']}/messages", json={"content": "Question with RAG"}
    )

    assert with_rag.status_code == 200
    assert with_rag.json()["rag_enabled"] is True
    assert with_rag.json()["rewritten_query"] is None
    assert retrieved_questions == ["Question with RAG"]
    assert "The local document states" in captured_messages[-1][0].content
    assert with_rag.json()["response"]["content"].startswith("The guide says retrieval")
    assert with_rag.json()["response"]["structured_data"] is None
    assert with_rag.json()["sources"] == [
        {
            "chunk_id": "guide-3",
            "source": "guide.md",
            "title": "Guide",
            "section": "Retrieval",
            "quote": "retrieval uses one best chunk",
        }
    ]
    stored = client.get(f"/sessions/{session['id']}").json()
    assert stored["messages"][-1]["sources"][0]["chunk_id"] == "guide-3"
    assert stored["messages"][-1]["sources"][0]["quote"] == "retrieval uses one best chunk"
    assert stored["messages"][-1]["rag_enabled"] is True
    assert stored["messages"][-1]["rewritten_query"] is None
    assert stored["messages"][-3]["rag_enabled"] is False


def test_empty_rag_context_uses_general_knowledge_with_knowledge_base_notice(
    monkeypatch, tmp_path: Path
) -> None:
    sessions = setup_runtime(monkeypatch, tmp_path)
    llm_configs = []

    def retrieve(question, settings=None, **kwargs) -> RagRetrievalResult:
        return RagRetrievalResult(rewritten_query="rephrased question for search")

    def complete(messages, config, tools=None):
        llm_configs.append(config)
        data = {
            "answer": "The knowledge base has no relevant information. Two plus two is four.",
            "citations": [],
        }
        return LLMResponse(
            content=json.dumps(data),
            structured_data=data,
            provider=ProviderName.OPENAI,
            model=config.model,
        )

    monkeypatch.setattr(service.document_indexing_composition.retriever, "retrieve", retrieve)
    monkeypatch.setattr(service.router, "complete", complete)
    client = ConversationTestClient(service.app)
    session = create_session(client, rag_enabled=True)
    saved_session = sessions.load(session["id"])
    saved_session.title = "No-context RAG test"
    sessions.save(saved_session)

    response = client.post(
        f"/sessions/{session['id']}/messages", json={"content": "A question with no evidence"}
    )

    assert response.status_code == 200
    assert response.json()["response"]["content"] == (
        "The knowledge base has no relevant information. Two plus two is four."
    )
    assert response.json()["sources"] == []
    assert response.json()["rag_enabled"] is True
    assert response.json()["rewritten_query"] == "rephrased question for search"
    assert "answer_mode" not in llm_configs[-1].structured_output.json_schema["properties"]
    stored = sessions.load(session["id"])
    assert stored.messages[-1].rag_enabled is True
    assert stored.messages[-1].rewritten_query == "rephrased question for search"


def test_retry_summarization_returns_and_persists_rag_snapshot(monkeypatch, tmp_path: Path) -> None:
    sessions = setup_runtime(monkeypatch, tmp_path)
    now = datetime.now(UTC)
    created = create_session(ConversationTestClient(service.app), rag_enabled=True)
    session = sessions.load(created["id"])
    session.config = session.config.model_copy(
        update={
            "context_management": ContextManagementConfig(
                recent_exchange_limit=1, summary_batch_exchange_count=1
            )
        }
    )
    session.messages = [
        ChatMessage(role="user", content="Older question"),
        ChatMessage(role="assistant", content="Older answer"),
        ChatMessage(role="user", content="Question to retry"),
    ]
    session.context = ConversationContext(
        events=[
            SummarizationEvent(
                id="failed-summary",
                status="failed",
                after_message_index=2,
                start_message_index=0,
                message_count=2,
                provider=ProviderName.OPENAI,
                model="test-model",
                duration_seconds=0,
                created_at=now,
                updated_at=now,
            )
        ]
    )
    sessions.save(session)

    def retrieve(question, settings=None, **kwargs) -> RagRetrievalResult:
        return RagRetrievalResult(rewritten_query="retry search query")

    def complete(messages, config, tools=None):
        if config.structured_output is None:
            return LLMResponse(content="Summary", provider=ProviderName.OPENAI, model=config.model)
        data = {"answer": "No matching evidence was found.", "citations": []}
        return LLMResponse(
            content=json.dumps(data),
            structured_data=data,
            provider=ProviderName.OPENAI,
            model=config.model,
        )

    monkeypatch.setattr(service.document_indexing_composition.retriever, "retrieve", retrieve)
    monkeypatch.setattr(service.router, "complete", complete)
    response = ConversationTestClient(service.app).post(
        f"/sessions/{created['id']}/summarization/retry"
    )

    assert response.status_code == 200
    assert response.json()["rag_enabled"] is True
    assert response.json()["rewritten_query"] == "retry search query"
    stored = sessions.load(created["id"])
    assert stored.messages[-1].rag_enabled is True
    assert stored.messages[-1].rewritten_query == "retry search query"


def test_rag_preserves_llm_response_when_chunk_is_below_similarity_threshold(
    monkeypatch, tmp_path: Path
) -> None:
    setup_runtime(monkeypatch, tmp_path)
    retriever = service.document_indexing_composition.retriever
    retrieved_chunk = RetrievedChunk(
        text="The fictional guide describes a blue kite.",
        source=KnowledgeSource(
            chunk_id="guide-1", source="fictional-guide.md", title="Guide", section="Items"
        ),
    )
    settings_seen = []
    llm_configs = []

    def search(_query, settings):
        settings_seen.append(settings)
        return [(settings.similarity_threshold - 0.01, retrieved_chunk)]

    def complete(messages, config, tools=None):
        llm_configs.append(config)
        data = {
            "answer": "The knowledge base has no relevant information about this personal detail.",
            "citations": [],
        }
        return LLMResponse(
            content=json.dumps(data),
            structured_data=data,
            provider=ProviderName.OPENAI,
            model=config.model,
        )

    monkeypatch.setattr(retriever, "_search", search)
    monkeypatch.setattr(service.router, "complete", complete)
    client = ConversationTestClient(service.app)
    session = create_session(client, rag_enabled=True)
    saved_session = service.sessions.load(session["id"])
    saved_session.title = "Below-threshold RAG test"
    service.sessions.save(saved_session)

    response = client.post(
        f"/sessions/{session['id']}/messages", json={"content": "Where is the blue kite?"}
    )

    assert response.status_code == 200
    content = response.json()["response"]["content"]
    assert content == "The knowledge base has no relevant information about this personal detail."
    assert response.json()["sources"] == []
    assert response.json()["rag_enabled"] is True
    assert settings_seen[0].similarity_threshold == 0.35
    assert "answer_mode" not in llm_configs[-1].structured_output.json_schema["properties"]


def test_invalid_rag_citation_retries_then_uses_no_evidence_policy(
    monkeypatch, tmp_path: Path
) -> None:
    sessions = setup_runtime(monkeypatch, tmp_path)
    retrieved_chunk = RetrievedChunk(
        text="The fictional handbook stores a blue kite in locker 4.",
        source=KnowledgeSource(
            chunk_id="handbook-4",
            source="fictional-handbook.md",
            title="Fictional Handbook",
            section="Storage",
        ),
    )
    citation_calls = 0
    fallback_calls = 0

    def retrieve(question: str) -> RetrievedChunk:
        return retrieved_chunk

    def complete(messages, config, tools=None):
        nonlocal citation_calls, fallback_calls
        if any(
            "Считай историю разговора и рабочую память контекстом, предоставленным пользователем"
            in item.content
            for item in messages
        ):
            fallback_calls += 1
            data = {
                "answer": "I could not find this personal detail in the knowledge base.",
                "citations": [],
            }
            return LLMResponse(
                content=json.dumps(data),
                structured_data=data,
                provider=ProviderName.OPENAI,
                model=config.model,
            )
        if (
            config.structured_output is not None
            and "citations" in config.structured_output.json_schema.get("properties", {})
        ):
            citation_calls += 1
        data = {
            "answer": "The blue kite is stored somewhere.",
            "citations": [{"chunk_id": "handbook-4", "quote": "blue kite in locker 4"}],
        }
        return LLMResponse(
            content=json.dumps(data),
            structured_data=data,
            provider=ProviderName.OPENAI,
            model=config.model,
        )

    monkeypatch.setattr(service.document_indexing_composition.retriever, "retrieve", retrieve)
    monkeypatch.setattr(service.router, "complete", complete)
    client = ConversationTestClient(service.app)
    session = create_session(client, rag_enabled=True)

    response = client.post(
        f"/sessions/{session['id']}/messages", json={"content": "Where is the blue kite?"}
    )

    assert response.status_code == 200
    content = response.json()["response"]["content"]
    assert content == "I could not find this personal detail in the knowledge base."
    assert "Не знаю." not in content
    assert response.json()["sources"] == []
    assert citation_calls == 2
    assert fallback_calls == 1
    saved_messages = sessions.load(session["id"]).messages
    assert saved_messages[-1].content == content
    assert saved_messages[-1].sources == []


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
