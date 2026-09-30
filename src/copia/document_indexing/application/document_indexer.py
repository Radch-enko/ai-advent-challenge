from __future__ import annotations

import json
import logging
import math
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from copia.document_indexing.data.document_loader import DocumentLoader
from copia.document_indexing.data.index_artifact_store import IndexArtifactStore
from copia.document_indexing.domain.chunking import (
    ChunkingStrategy,
    FixedSizeChunkingStrategy,
    StructureAwareChunkingStrategy,
)
from copia.document_indexing.domain.errors import DocumentIndexingError, IndexRunConflict
from copia.document_indexing.domain.models.document_chunk import DocumentChunk
from copia.document_indexing.domain.models.embedding_settings import EmbeddingSettings
from copia.document_indexing.domain.models.indexing_run_status import IndexingRunStatus
from copia.document_indexing.domain.models.source_document import SourceDocument
from copia.providers.application.embedding_router import EmbeddingRouter
from copia.providers.domain.contracts.embedding_provider import EmbeddingProvider
from copia.providers.domain.errors import ProviderError

logger = logging.getLogger(__name__)


class DocumentIndexer:
    BATCH_SIZE = 64

    def __init__(
        self,
        loader: DocumentLoader,
        artifact_store: IndexArtifactStore,
        providers: EmbeddingRouter,
    ) -> None:
        self._loader = loader
        self._artifacts = artifact_store
        self._providers = providers
        self._lock = threading.RLock()
        self._status = IndexingRunStatus()
        self._worker: threading.Thread | None = None

    @property
    def source_path(self) -> Path:
        return self._loader.documents_path

    def source_summary(self) -> tuple[int, int]:
        return self._loader.summary()

    def start(self, settings: EmbeddingSettings) -> IndexingRunStatus:
        provider = self._providers.provider(settings.provider)
        if not provider.is_configured:
            raise ProviderError(
                f"{provider.info.display_name} embedding provider is not configured"
            )
        with self._lock:
            if self._status.state == "running":
                raise IndexRunConflict("An indexing run is already active")
            run_id = uuid.uuid4().hex
            run_path = self._artifacts.create_run(run_id)
            self._status = IndexingRunStatus(
                run_id=run_id,
                state="running",
                stage="queued",
                artifact_path=str(run_path.resolve()),
                started_at=self._now(),
            )
            self._worker = threading.Thread(
                target=self._run,
                args=(run_id, run_path, settings, provider),
                name=f"document-index-{run_id[:8]}",
                daemon=True,
            )
            self._worker.start()
            return self._status.model_copy(deep=True)

    def status(self, run_id: str) -> IndexingRunStatus | None:
        with self._lock:
            if self._status.run_id != run_id:
                return None
            return self._status.model_copy(deep=True)

    def current_status(self) -> IndexingRunStatus:
        with self._lock:
            return self._status.model_copy(deep=True)

    def latest(self) -> dict[str, Any] | None:
        latest = self._artifacts.latest()
        if latest is None:
            return None
        manifest, run_path = latest
        return {
            "manifest": manifest,
            "artifact_path": str(run_path.resolve()),
            "comparison": (run_path / "comparison.md").read_text(encoding="utf-8"),
        }

    def close(self) -> None:
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join()

    def _run(
        self,
        run_id: str,
        run_path: Path,
        settings: EmbeddingSettings,
        provider: EmbeddingProvider,
    ) -> None:
        try:
            self._set_status(stage="scanning")
            documents = self._loader.load()
            if not documents:
                raise DocumentIndexingError(
                    "No non-empty .txt or .md documents were found in the source folder"
                )
            self._set_status(total_files=len(documents), stage="chunking")
            strategies: tuple[ChunkingStrategy, ...] = (
                FixedSizeChunkingStrategy(),
                StructureAwareChunkingStrategy(),
            )
            strategy_stats: dict[str, dict[str, float | int]] = {}
            embedding_dimension: int | None = None
            source_stats: list[dict[str, Any]] = []
            total_tokens = 0
            for document in documents:
                total_tokens += provider.count_tokens(document.text, settings.model)
                source_stats.append(
                    {
                        "source": document.source,
                        "title": document.title,
                        "size_bytes": document.size_bytes,
                        "characters": len(document.text),
                    }
                )
            for strategy in strategies:
                self._set_status(
                    stage=f"chunking:{strategy.id}",
                    processed_files=0,
                    total_files=len(documents),
                )
                strategy_stats[strategy.id], embedding_dimension = self._write_strategy(
                    run_path,
                    strategy,
                    documents,
                    provider,
                    settings.model,
                    embedding_dimension,
                )
            self._set_status(stage="saving")
            for strategy in strategies:
                self._artifacts.commit_jsonl(run_path, strategy.id)
            manifest = self._manifest(
                run_id,
                settings,
                documents,
                source_stats,
                total_tokens,
                embedding_dimension or 0,
                strategy_stats,
            )
            self._artifacts.write_json(run_path, "manifest.json", manifest)
            self._artifacts.write_text(
                run_path,
                "comparison.md",
                self._comparison_markdown(strategy_stats),
            )
            self._artifacts.publish_latest(run_id)
            self._set_status(state="completed", stage="completed", completed_at=self._now())
        except Exception as error:
            self._artifacts.remove_temporary_files(run_path)
            user_message = self._safe_error_message(error)
            logger.error("Document indexing run %s failed (%s)", run_id, type(error).__name__)
            self._set_status(
                state="failed",
                stage="failed",
                error=user_message,
                completed_at=self._now(),
            )

    def _write_strategy(
        self,
        run_path: Path,
        strategy: ChunkingStrategy,
        documents: list[SourceDocument],
        provider: EmbeddingProvider,
        model: str,
        current_dimension: int | None,
    ) -> tuple[dict[str, float | int], int | None]:
        output_path = self._artifacts.temporary_jsonl_path(run_path, strategy.id)
        chunk_count = 0
        token_total = 0
        max_tokens = 0
        with output_path.open("w", encoding="utf-8") as stream:
            for file_index, document in enumerate(documents, start=1):
                chunks = strategy.chunk(document, provider, model)
                self._set_status(
                    stage=f"embedding:{strategy.id}",
                    processed_files=file_index - 1,
                    total_files=len(documents),
                )
                for offset in range(0, len(chunks), self.BATCH_SIZE):
                    batch = chunks[offset : offset + self.BATCH_SIZE]
                    vectors = provider.embed([chunk.text for chunk in batch], model)
                    if len(vectors) != len(batch):
                        raise DocumentIndexingError(
                            f"Embedding provider returned the wrong vector count for {strategy.id}"
                        )
                    for chunk, vector in zip(batch, vectors, strict=True):
                        if not vector or any(not math.isfinite(value) for value in vector):
                            raise DocumentIndexingError(
                                "Embedding provider returned an invalid vector"
                            )
                        if current_dimension is None:
                            current_dimension = len(vector)
                        if len(vector) != current_dimension:
                            raise DocumentIndexingError(
                                "Embedding provider returned inconsistent vector dimensions"
                            )
                        stream.write(
                            json.dumps(
                                self._record(chunk, vector),
                                ensure_ascii=False,
                                allow_nan=False,
                            )
                            + "\n"
                        )
                        chunk_count += 1
                        token_total += chunk.token_count
                        max_tokens = max(max_tokens, chunk.token_count)
                self._set_status(
                    processed_files=file_index,
                    total_files=len(documents),
                )
            stream.flush()
            os.fsync(stream.fileno())
        return (
            {
                "chunk_count": chunk_count,
                "total_chunk_tokens": token_total,
                "average_chunk_tokens": round(token_total / chunk_count, 2) if chunk_count else 0,
                "max_chunk_tokens": max_tokens,
                "configured_max_tokens": strategy.max_tokens,
            },
            current_dimension,
        )

    @staticmethod
    def _record(chunk: DocumentChunk, vector: list[float]) -> dict[str, Any]:
        return {
            "text": chunk.text,
            "source": chunk.source,
            "title": chunk.title,
            "section": chunk.section,
            "chunk_id": chunk.chunk_id,
            "token_count": chunk.token_count,
            "embedding": vector,
        }

    @staticmethod
    def _manifest(
        run_id: str,
        settings: EmbeddingSettings,
        documents: list[SourceDocument],
        sources: list[dict[str, Any]],
        total_tokens: int,
        embedding_dimension: int,
        strategy_stats: dict[str, dict[str, float | int]],
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": run_id,
            "created_at": DocumentIndexer._now(),
            "provider": settings.provider,
            "model": settings.model,
            "embedding_dimension": embedding_dimension,
            "text_volume": {
                "file_count": len(documents),
                "bytes": sum(document.size_bytes for document in documents),
                "characters": sum(len(document.text) for document in documents),
                "tokens": total_tokens,
            },
            "sources": sources,
            "chunking": strategy_stats,
        }

    @staticmethod
    def _comparison_markdown(stats: dict[str, dict[str, float | int]]) -> str:
        lines = [
            "# Chunking comparison",
            "",
            "| Strategy | Chunks | Average tokens | Maximum tokens | Configured limit |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for strategy_id, values in stats.items():
            lines.append(
                "| "
                + " | ".join(
                    str(value)
                    for value in (
                        strategy_id,
                        values["chunk_count"],
                        values["average_chunk_tokens"],
                        values["max_chunk_tokens"],
                        values["configured_max_tokens"],
                    )
                )
                + " |"
            )
        lines.extend(["", "Both strategies were embedded with the same provider and model.", ""])
        return "\n".join(lines)

    @staticmethod
    def _safe_error_message(error: Exception) -> str:
        if isinstance(error, ProviderError):
            if error.status_code:
                return f"Embedding provider request failed (HTTP {error.status_code})"
            if "not configured" in str(error).lower():
                return "The selected embedding provider is not configured"
            return "Embedding provider request failed"
        if isinstance(error, DocumentIndexingError):
            return str(error)
        if isinstance(error, (OSError, UnicodeError)):
            return "Unable to read or write local indexing data"
        return "Document indexing failed. Check the backend log and retry."

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            self._status = self._status.model_copy(update=updates)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
