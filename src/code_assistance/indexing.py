import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from code_assistance.chunking import chunk_document
from code_assistance.documents import collect_documents
from code_assistance.errors import IndexCompatibilityError, ProviderError
from code_assistance.index_store import IndexStore
from code_assistance.models import Chunk
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
    ) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.store = store
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.max_file_bytes = max_file_bytes

    def sync(self, force: bool = False) -> SyncResult:
        collection = collect_documents(self.repository_root, self.max_file_bytes)
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

        changed_chunks = {path: chunk_document(current_documents[path]) for path in changed_paths}
        all_chunks = [chunk for chunks in changed_chunks.values() for chunk in chunks]
        vectors = self._embed_chunks(all_chunks)
        dimension = len(vectors[0]) if vectors else None

        previous_dimension = metadata.get("actual_dimensions")
        if (
            not reset
            and dimension is not None
            and previous_dimension
            and int(previous_dimension) != dimension
        ):
            reset = True
            changed_paths = set(current_documents)
            changed_chunks = {
                path: chunk_document(document) for path, document in current_documents.items()
            }
            all_chunks = [chunk for chunks in changed_chunks.values() for chunk in chunks]
            vectors = self._embed_chunks(all_chunks)
            dimension = len(vectors[0]) if vectors else None

        embedded_chunks: dict[str, list[tuple[Chunk, Sequence[float]]]] = {}
        offset = 0
        for path in changed_paths:
            chunks = changed_chunks[path]
            embedded_chunks[path] = []
            for chunk in chunks:
                embedded_chunks[path].append((chunk, vectors[offset]))
                offset += 1

        self.store.apply_sync(
            document_digests=current_digests,
            indexed_chunks=embedded_chunks,
            removed_paths=removed_paths,
            embedding_model=self.embedding_model,
            requested_dimensions=self.embedding_dimensions,
            actual_dimensions=dimension
            or (
                int(previous_dimension)
                if not reset and previous_dimension
                else self.embedding_dimensions
            ),
            reset=reset,
        )
        return SyncResult(
            indexed_document_count=len(current_documents),
            changed_document_count=len(changed_paths),
            removed_document_count=len(removed_paths),
            warnings=collection.warnings,
        )

    def _embed_chunks(self, chunks: list[Chunk]) -> list[list[float]]:
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
