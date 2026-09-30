from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copia.common.configuration import CopiaSettings
from copia.document_indexing.api.service_composition import DocumentIndexingServiceComposition
from copia.document_indexing.application.document_indexer import DocumentIndexer
from copia.document_indexing.data.document_loader import DocumentLoader
from copia.document_indexing.data.index_artifact_store import IndexArtifactStore
from copia.document_indexing.domain.chunking import (
    FixedSizeChunkingStrategy,
    StructureAwareChunkingStrategy,
)
from copia.document_indexing.domain.errors import IndexRunConflict
from copia.document_indexing.domain.models.embedding_settings import EmbeddingSettings
from copia.document_indexing.domain.models.source_document import SourceDocument
from copia.providers.application.embedding_router import EmbeddingRouter
from copia.providers.data.openai_embedding_provider import OpenAIEmbeddingProvider
from copia.providers.domain.models.embedding_provider_info import EmbeddingProviderInfo


class FakeEmbeddingProvider:
    info = EmbeddingProviderInfo("fake", "Fake embeddings", "fake-embedding-model")

    def __init__(self, *, block: bool = False) -> None:
        self.fail = False
        self.entered = threading.Event()
        self.release = threading.Event()
        if not block:
            self.release.set()

    @property
    def is_configured(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        return [self.info.default_model]

    def count_tokens(self, text: str, model: str) -> int:
        return len(text.split())

    def split_text(self, text: str, model: str, max_tokens: int, overlap_tokens: int) -> list[str]:
        words = text.split()
        if not words:
            return []
        chunks = []
        start = 0
        step = max_tokens - overlap_tokens
        while start < len(words):
            end = min(start + max_tokens, len(words))
            chunks.append(" ".join(words[start:end]))
            if end == len(words):
                break
            start += step
        return chunks

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        self.entered.set()
        self.release.wait(timeout=3)
        if self.fail:
            raise RuntimeError("provider failure")
        return [[float(len(text)), 1.0] for text in texts]

    def close(self) -> None:
        return None


def wait_until_finished(indexer: DocumentIndexer, run_id: str) -> str:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = indexer.status(run_id)
        if status is not None and status.state != "running":
            return status.state
        time.sleep(0.01)
    raise AssertionError("Indexing run did not finish")


def test_loader_reads_text_and_markdown_with_relative_metadata(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents"
    (documents_path / "nested").mkdir(parents=True)
    (documents_path / "nested" / "article.md").write_text("# A title\n\nText.", encoding="utf-8")
    (documents_path / "plain.txt").write_text("A text article.", encoding="utf-8")
    (documents_path / "ignored.pdf").write_bytes(b"pdf")

    documents = DocumentLoader(documents_path).load()

    assert [document.source for document in documents] == ["nested/article.md", "plain.txt"]
    assert documents[0].title == "article"
    assert documents[0].suffix == ".md"
    assert documents[0].size_bytes == len(b"# A title\n\nText.")


def test_document_source_path_defaults_to_data_root_and_accepts_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = CopiaSettings(data_root=tmp_path)
    assert settings.documents_path == settings.data_root.expanduser() / "documents"

    override = tmp_path / "custom-articles"
    monkeypatch.setenv("COPIA_DOCUMENTS_PATH", str(override))
    settings_with_override = CopiaSettings(data_root=tmp_path)
    assert settings_with_override.documents_path == override


def test_structure_strategy_preserves_markdown_sections_and_splits_long_blocks() -> None:
    provider = FakeEmbeddingProvider()
    long_body = " ".join(f"word{index}" for index in range(900))
    document = SourceDocument(
        source="guide.md",
        title="guide",
        suffix=".md",
        text=f"# Guide\n\nFirst paragraph.\n\n## Install\n\n{long_body}",
        size_bytes=0,
    )

    chunks = StructureAwareChunkingStrategy().chunk(document, provider, "fake-model")

    assert chunks[0].section == "Guide"
    assert "# Guide" in chunks[0].text
    assert "First paragraph." in chunks[0].text
    install_chunks = [chunk for chunk in chunks if chunk.section == "Guide / Install"]
    assert len(install_chunks) == 2
    assert all(chunk.token_count <= 680 for chunk in chunks)
    previous_words = install_chunks[0].text.split("\n\n", 1)[1].split()
    next_words = install_chunks[1].text.split("\n\n", 1)[1].split()
    assert previous_words[-64:] == next_words[:64]
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_fixed_strategy_obeys_token_limit_and_uses_sixty_four_token_overlap() -> None:
    provider = FakeEmbeddingProvider()
    document = SourceDocument(
        source="long.txt",
        title="long",
        suffix=".txt",
        text=" ".join(f"token{index}" for index in range(1200)),
        size_bytes=0,
    )

    chunks = FixedSizeChunkingStrategy().chunk(document, provider, "fake-model")

    assert len(chunks) == 3
    assert all(chunk.token_count <= 512 for chunk in chunks)
    assert chunks[0].text.split()[-64:] == chunks[1].text.split()[:64]
    assert all(chunk.source == "long.txt" and chunk.title == "long" for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_indexer_writes_jsonl_manifest_and_keeps_previous_success_after_failure(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents"
    documents_path.mkdir()
    (documents_path / "article.txt").write_text("one two three", encoding="utf-8")
    provider = FakeEmbeddingProvider()
    indexer = DocumentIndexer(
        DocumentLoader(documents_path),
        IndexArtifactStore(tmp_path / "document-index"),
        EmbeddingRouter({"fake": provider}),
    )
    settings = EmbeddingSettings(provider="fake", model="fake-model")

    first = indexer.start(settings)
    assert wait_until_finished(indexer, first.run_id or "") == "completed"
    latest = indexer.latest()
    assert latest is not None
    assert latest["manifest"]["embedding_dimension"] == 2
    assert latest["manifest"]["text_volume"]["file_count"] == 1
    run_path = Path(latest["artifact_path"])
    assert (run_path / "comparison.md").exists()
    for filename in ("fixed-size.jsonl", "structure-aware.jsonl"):
        rows = [json.loads(line) for line in (run_path / filename).read_text().splitlines()]
        assert rows
        assert {"text", "source", "title", "section", "chunk_id", "embedding"} <= rows[0].keys()
        assert rows[0]["source"] == "article.txt"
        assert len(rows[0]["embedding"]) == 2

    provider.fail = True
    failed = indexer.start(settings)
    assert wait_until_finished(indexer, failed.run_id or "") == "failed"
    assert indexer.latest()["manifest"]["run_id"] == first.run_id


def test_indexer_rejects_a_second_concurrent_run(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents"
    documents_path.mkdir()
    (documents_path / "article.txt").write_text("one two three", encoding="utf-8")
    provider = FakeEmbeddingProvider(block=True)
    indexer = DocumentIndexer(
        DocumentLoader(documents_path),
        IndexArtifactStore(tmp_path / "document-index"),
        EmbeddingRouter({"fake": provider}),
    )

    started = indexer.start(EmbeddingSettings(provider="fake", model="fake-model"))
    assert provider.entered.wait(timeout=2)
    with pytest.raises(IndexRunConflict):
        indexer.start(EmbeddingSettings(provider="fake", model="fake-model"))
    provider.release.set()
    assert wait_until_finished(indexer, started.run_id or "") == "completed"


def test_document_indexing_api_persists_settings_and_reports_run_progress(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents"
    documents_path.mkdir()
    (documents_path / "article.md").write_text("# Intro\n\nHello.", encoding="utf-8")
    provider = FakeEmbeddingProvider(block=True)
    composition = DocumentIndexingServiceComposition(
        tmp_path,
        documents_path,
        EmbeddingRouter({"fake": provider}),
    )
    app = FastAPI()
    app.include_router(composition.router())
    client = TestClient(app)

    initial = client.get("/document-indexing/settings")
    assert initial.status_code == 200
    assert initial.json()["source_file_count"] == 1
    catalog = client.get("/document-indexing/embedding-providers")
    assert catalog.json()["providers"][0]["models"] == ["fake-embedding-model"]
    saved = client.put(
        "/document-indexing/settings",
        json={"provider": "fake", "model": "custom-model-id"},
    )
    assert saved.status_code == 200
    assert saved.json()["model"] == "custom-model-id"
    assert client.get("/document-indexing/settings").json()["model"] == "custom-model-id"

    started = client.post("/document-indexing/runs")
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    assert provider.entered.wait(timeout=2)
    current = client.get("/document-indexing/runs/current")
    assert current.json()["run_id"] == run_id
    assert current.json()["state"] == "running"
    assert client.post("/document-indexing/runs").status_code == 409
    provider.release.set()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = client.get(f"/document-indexing/runs/{run_id}")
        if result.json()["state"] != "running":
            break
        time.sleep(0.01)
    assert result.json()["state"] == "completed"
    latest = client.get("/document-indexing/latest")
    assert latest.status_code == 200
    assert latest.json()["manifest"]["model"] == "custom-model-id"
    composition.close()


def test_openai_embedding_adapter_lists_models_sorts_vectors_and_splits_tokens() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "gpt-4o"},
                        {"id": "text-embedding-3-large"},
                        {"id": "text-embedding-3-small"},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [2.0, 2.5]},
                    {"index": 0, "embedding": [1.0, 1.5]},
                ]
            },
        )

    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        assert provider.list_models() == ["text-embedding-3-large", "text-embedding-3-small"]
        vectors = provider.embed(["first", "second"], "text-embedding-3-small")
        assert vectors == [[1.0, 1.5], [2.0, 2.5]]
        assert "first" in captured[1].content.decode()
    finally:
        provider.close()


def test_openai_embedding_adapter_uses_its_tokenizer_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEncoding:
        @staticmethod
        def encode(text: str, disallowed_special: object = ()) -> list[str]:
            return text.split()

        @staticmethod
        def decode(tokens: list[str]) -> str:
            return " ".join(tokens)

    from copia.providers.data import openai_embedding_provider

    monkeypatch.setattr(
        openai_embedding_provider,
        "_encoding_for_model",
        lambda model: FakeEncoding(),
    )
    provider = OpenAIEmbeddingProvider(api_key="test-key")
    try:
        assert provider.count_tokens("a b c", "custom-model") == 3
        chunks = provider.split_text(
            " ".join(str(index) for index in range(10)), "custom-model", 4, 1
        )
        assert [chunk.split() for chunk in chunks] == [
            ["0", "1", "2", "3"],
            ["3", "4", "5", "6"],
            ["6", "7", "8", "9"],
        ]
    finally:
        provider.close()
