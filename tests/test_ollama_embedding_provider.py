from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from copia.common.domain.models.rag_settings import RagSettings
from copia.document_indexing.application.document_indexer import DocumentIndexer
from copia.document_indexing.application.document_retriever import DocumentRetriever
from copia.document_indexing.data.document_loader import DocumentLoader
from copia.document_indexing.data.index_artifact_store import IndexArtifactStore
from copia.document_indexing.domain.models.embedding_settings import EmbeddingSettings
from copia.providers.application.embedding_router import EmbeddingRouter
from copia.providers.data.ollama_embedding_provider import OllamaEmbeddingProvider
from copia.providers.domain.errors import ProviderError


def test_default_embedding_router_exposes_ollama() -> None:
    router = EmbeddingRouter()
    assert router.provider("ollama").info.default_model == "qwen3-embedding:0.6b"
    router.close()


def test_ollama_embedding_adapter_lists_models_and_orders_batch_vectors() -> None:
    requests: list[tuple[str, dict[str, object] | None]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.method == "POST" else None
        requests.append((str(request.url), payload))
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "qwen3-embedding:0.6b"}]})
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0, 1]},
                    {"index": 0, "embedding": [1, 0]},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434", client=client)
    assert provider.is_configured
    assert provider.list_models() == ["qwen3-embedding:0.6b"]
    assert provider.embed(
        ["Fictional amber note", "Fictional blue note"], "qwen3-embedding:0.6b"
    ) == [
        [1.0, 0.0],
        [0.0, 1.0],
    ]
    assert requests == [
        ("http://localhost:11434/v1/models", None),
        (
            "http://localhost:11434/v1/embeddings",
            {
                "model": "qwen3-embedding:0.6b",
                "input": ["Fictional amber note", "Fictional blue note"],
            },
        ),
    ]
    provider.close()


def test_ollama_embedding_adapter_reports_http_error_without_document_text() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(404, json={"error": "missing"})
        )
    )
    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434", client=client)

    with pytest.raises(ProviderError, match="status 404") as caught:
        provider.embed(["Fictional private note"], "missing-model")

    assert "Fictional private note" not in str(caught.value)
    provider.close()


def test_ollama_index_and_query_use_the_same_local_embedding_model(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://localhost:11434/v1/embeddings"
        payload = json.loads(request.content)
        calls.append(payload)
        data = []
        for index, text in enumerate(payload["input"]):
            vector = [1.0, 0.0] if "amber" in text.lower() else [0.0, 1.0]
            data.append({"index": index, "embedding": vector})
        return httpx.Response(200, json={"data": data})

    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "amber.md").write_text("# Amber\n\nA fictional amber compass.", encoding="utf-8")
    (documents / "blue.md").write_text("# Blue\n\nA fictional blue compass.", encoding="utf-8")
    provider = OllamaEmbeddingProvider(
        base_url="http://localhost:11434",
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    router = EmbeddingRouter({"ollama": provider})
    artifacts = IndexArtifactStore(tmp_path / "index")
    indexer = DocumentIndexer(DocumentLoader(documents), artifacts, router)

    run = indexer.start(EmbeddingSettings(provider="ollama", model="qwen3-embedding:0.6b"))
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = indexer.status(run.run_id or "")
        if status is not None and status.state != "running":
            break
        time.sleep(0.01)
    assert status is not None and status.state == "completed"

    result = DocumentRetriever(artifacts, router).retrieve(
        "Where is the amber compass?",
        RagSettings(query_rewrite_enabled=False),
    )
    assert result.context_chunks[0].source.source == "amber.md"
    assert all(call["model"] == "qwen3-embedding:0.6b" for call in calls)
    assert len(calls) >= 2
    indexer.close()
    router.close()
