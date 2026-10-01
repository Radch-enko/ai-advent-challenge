from __future__ import annotations

import json
import math
from typing import Any

from copia.common.domain.services.llm_context_builder import LLMContextBuilder
from copia.common.domain.services.prompt_resources import render_prompt
from copia.document_indexing.data.index_artifact_store import IndexArtifactStore
from copia.document_indexing.domain.errors import DocumentRetrievalError
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.providers.application.embedding_router import EmbeddingRouter
from copia.providers.domain.errors import ProviderError
from copia.sessions.domain.models.chat_message import ChatMessage


class DocumentRetriever:
    def __init__(self, artifact_store: IndexArtifactStore, providers: EmbeddingRouter) -> None:
        self._artifacts = artifact_store
        self._providers = providers

    def retrieve(self, question: str) -> RetrievedChunk:
        if not question.strip():
            raise DocumentRetrievalError("RAG search requires a non-empty question")

        try:
            return self._retrieve(question)
        except DocumentRetrievalError:
            raise
        except ProviderError as error:
            raise DocumentRetrievalError(
                "RAG search failed. Check the embedding provider configuration and retry."
            ) from error
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError) as error:
            raise DocumentRetrievalError(
                "RAG search failed because the local document index is unavailable or invalid."
            ) from error
        except Exception as error:
            raise DocumentRetrievalError(
                "RAG search failed. Check the embedding provider and document index, then retry."
            ) from error

    def contextualize(
        self,
        messages: list[ChatMessage],
        retrieved_chunk: RetrievedChunk,
    ) -> list[ChatMessage]:
        serialized_chunk = json.dumps(
            {
                "chunk_id": retrieved_chunk.source.chunk_id,
                "source": retrieved_chunk.source.source,
                "title": retrieved_chunk.source.title,
                "section": retrieved_chunk.source.section,
                "text": retrieved_chunk.text,
            },
            ensure_ascii=False,
        )
        context = render_prompt(
            "copia.document_indexing",
            "rag_context.md",
            retrieved_chunk_json=serialized_chunk,
        )
        return LLMContextBuilder.with_additional_system_context(messages, context)

    def _retrieve(self, question: str) -> RetrievedChunk:
        latest = self._artifacts.latest()
        if latest is None:
            raise DocumentRetrievalError(
                "RAG is enabled, but no completed document index is available."
            )

        manifest, run_path = latest
        provider_id = _required_string(manifest, "provider")
        model = _required_string(manifest, "model")
        dimension = manifest.get("embedding_dimension")
        if not isinstance(dimension, int) or dimension <= 0:
            raise ValueError("Invalid embedding dimension")

        provider = self._providers.provider(provider_id)
        if not provider.is_configured:
            raise ProviderError("Embedding provider is not configured")
        query_vectors = provider.embed([question], model)
        if len(query_vectors) != 1:
            raise ValueError("Embedding provider returned the wrong vector count")
        query_vector = _validated_vector(query_vectors[0], dimension)
        query_norm = math.sqrt(math.fsum(value * value for value in query_vector))
        if query_norm == 0:
            raise ValueError("Embedding provider returned a zero vector")

        index_path = run_path / "structure-aware.jsonl"
        best: tuple[float, RetrievedChunk] | None = None
        with index_path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                record = json.loads(line)
                chunk = _parse_chunk(record, dimension)
                vector = _validated_vector(record.get("embedding"), dimension)
                vector_norm = math.sqrt(math.fsum(value * value for value in vector))
                if vector_norm == 0:
                    raise ValueError("Index contains a zero vector")
                score = math.fsum(
                    left * right for left, right in zip(query_vector, vector, strict=True)
                ) / (query_norm * vector_norm)
                if best is None or score > best[0]:
                    best = (score, chunk)

        if best is None:
            raise DocumentRetrievalError(
                "RAG is enabled, but the document index contains no chunks."
            )
        return best[1]


def _required_string(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid {field}")
    return value


def _validated_vector(value: Any, expected_dimension: int) -> list[float]:
    if not isinstance(value, list) or len(value) != expected_dimension:
        raise ValueError("Invalid embedding vector dimension")
    if any(not isinstance(item, (int, float)) or not math.isfinite(item) for item in value):
        raise ValueError("Invalid embedding vector")
    return [float(item) for item in value]


def _parse_chunk(record: Any, expected_dimension: int) -> RetrievedChunk:
    if not isinstance(record, dict):
        raise ValueError("Invalid index record")
    text = _required_string(record, "text")
    source = _required_string(record, "source")
    title = _required_string(record, "title")
    section = record.get("section", "")
    chunk_id = _required_string(record, "chunk_id")
    if not isinstance(section, str):
        raise ValueError("Invalid section")
    return RetrievedChunk(
        text=text,
        source={"chunk_id": chunk_id, "source": source, "title": title, "section": section},
    )
