import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from code_assistance.chunking import chunk_document
from code_assistance.documents import DocumentCollection, collect_documents
from code_assistance.errors import IndexCompatibilityError, ProviderError
from code_assistance.index_store import IndexStore
from code_assistance.models import Chunk, Document
from code_assistance.ports import EmbeddingProvider

EMBEDDING_BATCH_SIZE = 64


@dataclass(frozen=True)
class SyncResult:
    indexed_document_count: int
    changed_document_count: int
    removed_document_count: int
    warnings: tuple[str, ...]


def index_database_path(repository_root: Path, index_directory: Path) -> Path:
    root_key = hashlib.sha256(str(repository_root.resolve()).encode("utf-8")).hexdigest()
    return index_directory / f"{root_key}.sqlite3"


class IndexSynchronizer:
    def __init__(
        self,
        repository_root: Path,
        store: IndexStore,
        embedding_provider: EmbeddingProvider,
        embedding_model: str,
        embedding_dimensions: int | None,
        max_file_bytes: int,
        collector: Callable[[Path, int], DocumentCollection] = collect_documents,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.store = store
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.max_file_bytes = max_file_bytes
        self.collector = collector
        self.progress = progress

    def sync(self, force: bool = False) -> SyncResult:
        collection = self.collector(self.repository_root, self.max_file_bytes)
        current_documents = {document.path: document for document in collection.documents}
        current_digests = {path: document.digest for path, document in current_documents.items()}
        old_digests = self.store.document_digests()
        metadata = self.store.metadata()
        model_compatible = self.store.is_compatible(self.embedding_model, self.embedding_dimensions)
        reset = force or not model_compatible
        changed_paths = (
            set(current_documents)
            if reset
            else {
                path
                for path, document in current_documents.items()
                if old_digests.get(path) != document.digest
            }
        )
        removed_paths = set(old_digests) - set(current_documents)

        previous_dimension = metadata.get("actual_dimensions")
        while True:
            groups = self._document_groups(current_documents, changed_paths)
            cached_count = len(current_documents) - len(changed_paths)
            if self.progress is not None:
                self.progress(cached_count, len(current_documents))
            completed = 0
            actual_dimension = int(previous_dimension) if not reset and previous_dimension else None
            restart = False
            embedded_any = False
            for group in groups:
                chunks = {path: chunk_document(current_documents[path]) for path in group}
                ordered = [chunk for path in group for chunk in chunks[path]]
                vectors = self._embed_chunks(ordered)
                dimension = len(vectors[0]) if vectors else None
                if dimension is not None and actual_dimension is not None:
                    if dimension != actual_dimension:
                        if not reset and not embedded_any:
                            reset = True
                            changed_paths = set(current_documents)
                            restart = True
                            break
                        raise IndexCompatibilityError(
                            "The embedding provider changed dimensions during indexing."
                        )
                actual_dimension = dimension or actual_dimension
                indexed_chunks: dict[str, list[tuple[Chunk, Sequence[float]]]] = {}
                offset = 0
                for path in group:
                    indexed_chunks[path] = []
                    for chunk in chunks[path]:
                        indexed_chunks[path].append((chunk, vectors[offset]))
                        offset += 1
                self.store.apply_sync(
                    document_digests={path: current_digests[path] for path in group},
                    indexed_chunks=indexed_chunks,
                    removed_paths=removed_paths if completed == 0 else set(),
                    embedding_model=self.embedding_model,
                    requested_dimensions=self.embedding_dimensions,
                    actual_dimensions=actual_dimension or self.embedding_dimensions,
                    reset=reset if completed == 0 else False,
                )
                completed += len(group)
                embedded_any = embedded_any or bool(vectors)
                if self.progress is not None:
                    self.progress(cached_count + completed, len(current_documents))
            if restart:
                continue
            if not groups:
                self.store.apply_sync(
                    document_digests={},
                    indexed_chunks={},
                    removed_paths=removed_paths,
                    embedding_model=self.embedding_model,
                    requested_dimensions=self.embedding_dimensions,
                    actual_dimensions=actual_dimension or self.embedding_dimensions,
                    reset=reset,
                )
            break
        if self.progress is not None:
            self.progress(len(current_documents), len(current_documents))
        return SyncResult(
            indexed_document_count=len(current_documents),
            changed_document_count=len(changed_paths),
            removed_document_count=len(removed_paths),
            warnings=collection.warnings,
        )

    @staticmethod
    def _document_groups(documents: dict[str, Document], paths: set[str]) -> list[list[str]]:
        groups: list[list[str]] = []
        group: list[str] = []
        chunk_count = 0
        for path in sorted(paths):
            count = len(chunk_document(documents[path]))
            if group and chunk_count + count > EMBEDDING_BATCH_SIZE:
                groups.append(group)
                group = []
                chunk_count = 0
            group.append(path)
            chunk_count += count
        if group:
            groups.append(group)
        return groups

    def _embed_chunks(
        self, chunks: list[Chunk], progress: Callable[[int], None] | None = None
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        for offset in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[offset : offset + EMBEDDING_BATCH_SIZE]
            batch_vectors = self.embedding_provider.embed(
                [chunk.text for chunk in batch],
                dimensions=self.embedding_dimensions,
            )
            if len(batch_vectors) != len(batch):
                raise ProviderError("The embedding provider returned an unexpected vector count.")
            vectors.extend(batch_vectors)
            if progress is not None:
                progress(len(vectors))

        if not vectors:
            return []
        expected_dimension = len(vectors[0])
        if expected_dimension == 0:
            raise ProviderError("The embedding provider returned an empty vector.")
        if (
            self.embedding_dimensions is not None
            and expected_dimension != self.embedding_dimensions
        ):
            raise IndexCompatibilityError(
                "The embedding provider returned a dimension different from the configured value."
            )
        if any(len(vector) != expected_dimension for vector in vectors):
            raise ProviderError("The embedding provider returned inconsistent vector dimensions.")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for vector in vectors
            for value in vector
        ):
            raise ProviderError("The embedding provider returned a non-finite vector value.")
        return vectors
