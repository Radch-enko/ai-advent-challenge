from __future__ import annotations

import json
from pathlib import Path

from conversation_test_client import ConversationTestClient

from copia import service
from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.common.domain.models.rag_diagnostics import RagDiagnosticCandidate
from copia.conversations.application.conversation_store import ConversationStore
from copia.document_indexing.domain.models.rag_retrieval_result import RagRetrievalResult
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.data.sessions_repository import SessionsRepository


def _setup(monkeypatch, tmp_path: Path) -> tuple[ConversationTestClient, SessionsRepository, str]:
    sessions = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "conversation_store", ConversationStore())
    client = ConversationTestClient(service.app)
    session = client.post(
        "/sessions",
        json={
            "config": {"name": "Demo", "provider": "openai", "model": "demo-model"},
            "rag_enabled": True,
        },
    ).json()
    saved = sessions.load(session["id"])
    saved.title = "Fictional RAG diagnostics"
    saved.rag_settings = saved.rag_settings.model_copy(update={"query_rewrite_enabled": False})
    sessions.save(saved)
    return client, sessions, session["id"]


def _source(score: float) -> KnowledgeSource:
    return KnowledgeSource(
        chunk_id="fictional-1",
        source="fictional-guide.md",
        title="Fictional Guide",
        section="Compass",
        similarity_score=score,
    )


def _complete(answer: str, citations: list[dict[str, str]]):
    def complete(_messages, config, tools=None):
        data = {"answer": answer, "citations": citations}
        return LLMResponse(
            content=json.dumps(data),
            structured_data=data,
            provider=ProviderName.OPENAI,
            model=config.model,
        )

    return complete


def test_below_threshold_diagnostics_are_returned_and_persisted(
    monkeypatch, tmp_path: Path
) -> None:
    client, sessions, session_id = _setup(monkeypatch, tmp_path)
    retriever = service.document_indexing_composition.retriever
    candidate = RetrievedChunk(text="A fictional compass.", source=_source(0.34))
    monkeypatch.setattr(retriever, "_search", lambda _query, _settings: [(0.34, candidate)])
    monkeypatch.setattr(service.router, "complete", _complete("No matching compass found.", []))

    response = client.post(
        f"/sessions/{session_id}/messages", json={"content": "Find a fictional compass"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert body["rag_diagnostics"] == {
        "reason": "below_threshold",
        "similarity_threshold": 0.35,
        "query_fallback_used": False,
        "candidates": [
            {
                "source": {
                    "chunk_id": "fictional-1",
                    "source": "fictional-guide.md",
                    "title": "Fictional Guide",
                    "section": "Compass",
                    "similarity_score": 0.34,
                    "selected_for_context": False,
                },
                "text_preview": "A fictional compass.",
            }
        ],
    }
    assert sessions.load(session_id).messages[-1].rag_diagnostics is not None
    assert (
        client.get(f"/sessions/{session_id}").json()["messages"][-1]["rag_diagnostics"]
        == body["rag_diagnostics"]
    )


def test_citation_failure_reports_accepted_candidates(monkeypatch, tmp_path: Path) -> None:
    client, _, session_id = _setup(monkeypatch, tmp_path)
    source = _source(0.82).model_copy(update={"selected_for_context": True})
    chunk = RetrievedChunk(text="A fictional compass is in the blue box.", source=source)
    result = RagRetrievalResult(
        context_chunks=[chunk],
        filtered_sources=[source],
        diagnostic_candidates=[
            RagDiagnosticCandidate(source=source, text_preview=chunk.text[:240])
        ],
    )
    monkeypatch.setattr(
        service.document_indexing_composition.retriever,
        "retrieve",
        lambda *_args, **_kwargs: result,
    )
    rag_completion_calls = 0
    no_evidence_completion_calls = 0
    complete = _complete("The fictional compass is in the blue box.", [])

    def complete_with_invalid_citations(messages, config, tools=None):
        nonlocal rag_completion_calls, no_evidence_completion_calls
        message_text = "\n".join(message.content for message in messages)
        if "Найденные фрагменты документов (JSON)" in message_text:
            rag_completion_calls += 1
        if "в базе знаний не нашлось подходящих сведений" in message_text:
            no_evidence_completion_calls += 1
        return complete(messages, config, tools)

    monkeypatch.setattr(service.router, "complete", complete_with_invalid_citations)

    response = client.post(
        f"/sessions/{session_id}/messages", json={"content": "Where is the compass?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert rag_completion_calls == 2
    assert no_evidence_completion_calls == 0
    assert body["response"]["content"].startswith(
        "⚠️ Цитаты не прошли проверку. Ответ модели может быть ошибочным."
    )
    assert "The fictional compass is in the blue box." in body["response"]["content"]
    assert body["sources"] == []
    assert body["rag_diagnostics"]["reason"] == "citation_validation_failed"
    assert body["rag_diagnostics"]["similarity_threshold"] == 0.35
    assert body["rag_diagnostics"]["candidates"][0]["source"]["similarity_score"] == 0.82
    assert body["rag_diagnostics"]["candidates"][0]["text_preview"].startswith(
        "A fictional compass"
    )


def test_diagnostics_candidates_follow_original_query_retry(monkeypatch, tmp_path: Path) -> None:
    _, sessions, session_id = _setup(monkeypatch, tmp_path)
    retriever = service.document_indexing_composition.retriever
    settings = sessions.load(session_id).rag_settings.model_copy(
        update={"query_rewrite_enabled": True}
    )
    searches: list[str] = []

    def search(query, _settings):
        searches.append(query)
        score = 0.21 if query == "rewritten compass" else 0.34
        return [(score, RetrievedChunk(text="A fictional compass.", source=_source(score)))]

    monkeypatch.setattr(retriever, "_rewrite_query", lambda *_args: "rewritten compass")
    monkeypatch.setattr(retriever, "_search", search)

    result = retriever.retrieve_with_settings("original compass", settings)

    assert searches == ["rewritten compass", "original compass"]
    assert result.query_fallback_used is True
    assert result.context_chunks == []
    assert result.diagnostic_candidates[0].source.similarity_score == 0.34
