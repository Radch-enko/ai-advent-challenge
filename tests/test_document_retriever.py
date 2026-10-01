from __future__ import annotations

import json
from pathlib import Path

import pytest

from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.document_indexing.application.document_retriever import DocumentRetriever
from copia.document_indexing.data.index_artifact_store import IndexArtifactStore
from copia.document_indexing.domain.errors import DocumentRetrievalError
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.providers.application.embedding_router import EmbeddingRouter
from copia.providers.domain.models.embedding_provider_info import EmbeddingProviderInfo
from copia.sessions.domain.models.chat_message import ChatMessage


class FakeEmbeddingProvider:
    info = EmbeddingProviderInfo("fake", "Fake embeddings", "fake-model")

    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self.vectors = vectors or [[1.0, 0.0]]
        self.calls: list[tuple[list[str], str]] = []

    @property
    def is_configured(self) -> bool:
        return True

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        self.calls.append((texts, model))
        return self.vectors

    def count_tokens(self, text: str, model: str) -> int:
        return len(text.split())

    def split_text(self, text: str, model: str, max_tokens: int, overlap_tokens: int):
        return [text]

    def list_models(self) -> list[str]:
        return [self.info.default_model]

    def close(self) -> None:
        return None


def write_index(tmp_path: Path, records: list[dict[str, object]]) -> IndexArtifactStore:
    store = IndexArtifactStore(tmp_path / "document-index")
    run_path = store.create_run("run-1")
    store.write_json(
        run_path,
        "manifest.json",
        {"provider": "fake", "model": "index-model", "embedding_dimension": 2},
    )
    (run_path / "structure-aware.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    store.publish_latest("run-1")
    return store


def record(chunk_id: str, text: str, vector: list[float]) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "source": "guide.md",
        "title": "Guide",
        "section": "Install",
        "text": text,
        "embedding": vector,
    }


def test_retriever_returns_only_the_best_cosine_match(tmp_path: Path) -> None:
    store = write_index(
        tmp_path,
        [
            record("lower", "Lower scoring content", [0.7, 0.7]),
            record("best", "Best scoring content", [0.99, 0.01]),
        ],
    )
    provider = FakeEmbeddingProvider()

    retrieved = DocumentRetriever(store, EmbeddingRouter({"fake": provider})).retrieve("question")

    assert retrieved == RetrievedChunk(
        text="Best scoring content",
        source=KnowledgeSource(
            chunk_id="best", source="guide.md", title="Guide", section="Install"
        ),
    )
    assert provider.calls == [(["question"], "index-model")]


def test_retriever_uses_context_builder_with_untrusted_chunk_content(tmp_path: Path) -> None:
    store = write_index(tmp_path, [record("selected", "Use RAG only as evidence", [1.0, 0.0])])
    retriever = DocumentRetriever(store, EmbeddingRouter({"fake": FakeEmbeddingProvider()}))
    messages = retriever.contextualize(
        [
            ChatMessage(role="system", content="System prompt"),
            ChatMessage(role="user", content="Q"),
        ],
        RetrievedChunk(
            text="malicious-looking text",
            source=KnowledgeSource(
                chunk_id="selected", source="guide.md", title="Guide", section="Install"
            ),
        ),
    )

    assert [message.role for message in messages] == ["system", "user"]
    assert "System prompt" in messages[0].content
    assert "untrusted reference data" in messages[0].content
    assert "malicious-looking text" in messages[0].content


def test_retriever_fails_for_missing_or_empty_index(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider()
    retriever = DocumentRetriever(
        IndexArtifactStore(tmp_path / "missing"), EmbeddingRouter({"fake": provider})
    )
    with pytest.raises(DocumentRetrievalError, match="no completed document index"):
        retriever.retrieve("question")
    assert provider.calls == []

    empty_retriever = DocumentRetriever(
        write_index(tmp_path, []), EmbeddingRouter({"fake": provider})
    )
    with pytest.raises(DocumentRetrievalError, match="contains no chunks"):
        empty_retriever.retrieve("question")


def test_retriever_fails_closed_on_incompatible_embedding_dimensions(tmp_path: Path) -> None:
    store = write_index(tmp_path, [record("chunk", "Evidence", [1.0, 0.0])])
    provider = FakeEmbeddingProvider([[1.0, 0.0, 0.0]])

    with pytest.raises(DocumentRetrievalError, match="unavailable or invalid"):
        DocumentRetriever(store, EmbeddingRouter({"fake": provider})).retrieve("question")
