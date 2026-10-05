from datetime import UTC, datetime

import pytest

from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.document_indexing.application.rag_citations import (
    RagCitationValidationError,
    rag_answer_schema,
    validate_rag_response,
)
from copia.document_indexing.domain.models.rag_retrieval_result import RagRetrievalResult
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage


def test_rag_schema_removes_legacy_answer_mode_from_base_schema() -> None:
    schema = rag_answer_schema(
        {
            "type": "object",
            "properties": {"answer_mode": {"type": "string"}},
            "required": ["answer_mode"],
        },
        allow_uncited_fallback=True,
    )

    assert "answer_mode" not in schema["properties"]
    assert schema["required"] == ["answer", "citations"]


def test_uncited_fallback_is_rejected_when_retrieved_chunks_exist() -> None:
    source = KnowledgeSource(chunk_id="guide-1", source="guide.md", title="Guide")
    result = RagRetrievalResult(
        context_chunks=[RetrievedChunk(text="A fictional fact.", source=source)],
        filtered_sources=[source],
    )
    response = LLMResponse(
        content="A fictional answer.",
        structured_data={"answer": "A fictional answer.", "citations": []},
        provider=ProviderName.OPENAI,
        model="test-model",
    )

    with pytest.raises(RagCitationValidationError):
        validate_rag_response(response, result, allow_uncited_fallback=True)


def test_branch_transcripts_preserve_rag_metadata_and_load_legacy_messages(tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    answer = ChatMessage(
        role="assistant",
        content="A readable answer",
        rag_enabled=True,
        rewritten_query="normalized search query",
    )

    repository.save_branch("session", "branch", [answer])
    restored = repository.load_branch("session", "branch")
    legacy = ChatMessage.model_validate(
        {
            "role": "assistant",
            "content": "Legacy response",
            "created_at": datetime.now(UTC),
        }
    )

    assert restored[0].rag_enabled is True
    assert restored[0].rewritten_query == "normalized search query"
    assert legacy.rag_enabled is None
    assert legacy.rewritten_query is None
