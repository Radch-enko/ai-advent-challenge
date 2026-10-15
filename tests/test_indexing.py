from pathlib import Path

import pytest

from code_assistance.errors import IndexCorruptionError, ProviderError
from code_assistance.index_store import IndexStore
from code_assistance.indexing import IndexSynchronizer, index_database_path
from tests.conftest import FakeEmbeddings


def _synchronizer(
    repository: Path,
    index_directory: Path,
    embeddings: FakeEmbeddings,
    model: str = "test-embedding",
    dimensions: int | None = None,
) -> tuple[IndexStore, IndexSynchronizer]:
    store = IndexStore(index_database_path(repository, index_directory))
    synchronizer = IndexSynchronizer(
        repository_root=repository,
        store=store,
        embedding_provider=embeddings,
        embedding_model=model,
        embedding_dimensions=dimensions,
        max_file_bytes=100_000,
    )
    return store, synchronizer


def test_readme_and_docs_are_embedded_and_repositories_are_isolated(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    first = git_repository
    (first / "README.md").write_text("General repository overview.", encoding="utf-8")
    (first / "docs").mkdir()
    (first / "docs" / "architecture.md").write_text(
        "The project layout is documented here.", encoding="utf-8"
    )
    second = tmp_path / "second"
    second.mkdir()
    import subprocess

    subprocess.run(["git", "init", "--quiet", str(second)], check=True)
    (second / "docs").mkdir()
    (second / "docs" / "billing.md").write_text(
        "The payment service handles invoices.", encoding="utf-8"
    )

    first_store, first_sync = _synchronizer(first, tmp_path / "indexes", fake_embeddings)
    second_store, second_sync = _synchronizer(second, tmp_path / "indexes", fake_embeddings)
    first_result = first_sync.sync()
    second_result = second_sync.sync()

    assert first_result.indexed_document_count == 2
    assert second_result.indexed_document_count == 1
    assert first_store.document_count() == 2
    assert second_store.document_count() == 1
    embedded_text = [text for batch in fake_embeddings.calls for text in batch]
    assert any("General repository overview" in text for text in embedded_text)
    assert any("project layout" in text for text in embedded_text)
    assert any("payment service" in text for text in embedded_text)
    assert first_store.database_path != second_store.database_path


def test_sync_updates_changed_files_and_removes_deleted_files(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    changed = docs / "architecture.md"
    removed = docs / "billing.md"
    changed.write_text("The architecture describes the project layout.", encoding="utf-8")
    removed.write_text("The payment service handles invoices.", encoding="utf-8")
    store, synchronizer = _synchronizer(git_repository, tmp_path / "indexes", fake_embeddings)
    synchronizer.sync()
    initial_call_count = len(fake_embeddings.calls)

    changed.write_text("The new architecture explains the module structure.", encoding="utf-8")
    removed.unlink()
    result = synchronizer.sync()

    assert result.changed_document_count == 1
    assert result.removed_document_count == 1
    assert store.document_count() == 1
    assert len(fake_embeddings.calls) == initial_call_count + 1


def test_embedding_model_change_rebuilds_index_but_chat_model_is_not_an_index_input(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("The project layout.", encoding="utf-8")
    store, original = _synchronizer(git_repository, tmp_path / "indexes", fake_embeddings)
    original.sync()
    initial_call_count = len(fake_embeddings.calls)

    same_embedding_model, same_embedding_sync = _synchronizer(
        git_repository, tmp_path / "indexes", fake_embeddings, model="test-embedding"
    )
    same_result = same_embedding_sync.sync()
    changed_embedding_sync = IndexSynchronizer(
        repository_root=git_repository,
        store=store,
        embedding_provider=fake_embeddings,
        embedding_model="different-embedding",
        embedding_dimensions=None,
        max_file_bytes=100_000,
    )
    changed_result = changed_embedding_sync.sync()

    assert same_embedding_model.document_count() == 1
    assert same_result.changed_document_count == 0
    assert len(fake_embeddings.calls) == initial_call_count + 1
    assert changed_result.changed_document_count == 1
    assert store.is_compatible("different-embedding", None)


def test_empty_documents_and_removed_files_do_not_call_embeddings(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    store, synchronizer = _synchronizer(git_repository, tmp_path / "indexes", fake_embeddings)

    result = synchronizer.sync()

    assert result.indexed_document_count == 0
    assert result.changed_document_count == 0
    assert not fake_embeddings.calls
    assert store.document_count() == 0


def test_embedding_dimension_change_rebuilds_existing_index(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("The project structure is documented.", encoding="utf-8")
    store, first_sync = _synchronizer(
        git_repository,
        tmp_path / "indexes",
        fake_embeddings,
        dimensions=2,
    )
    first_sync.sync()

    _, changed_sync = _synchronizer(
        git_repository,
        tmp_path / "indexes",
        fake_embeddings,
        dimensions=3,
    )
    result = changed_sync.sync()

    assert result.changed_document_count == 1
    assert store.metadata()["requested_dimensions"] == "3"
    assert store.metadata()["actual_dimensions"] == "3"


def test_embedding_failure_does_not_replace_previous_index(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    guide = docs / "guide.md"
    guide.write_text("The project structure is documented.", encoding="utf-8")
    store, synchronizer = _synchronizer(
        git_repository,
        tmp_path / "indexes",
        fake_embeddings,
    )
    synchronizer.sync()
    previous_digest = store.document_digests()["docs/guide.md"]

    guide.write_text("A changed project structure is documented.", encoding="utf-8")

    class FailingEmbeddings:
        def embed(
            self,
            texts: list[str] | tuple[str, ...],
            dimensions: int | None = None,
        ) -> list[list[float]]:
            del texts, dimensions
            raise ProviderError("The fake embedding service is unavailable.")

    failing_sync = IndexSynchronizer(
        repository_root=git_repository,
        store=store,
        embedding_provider=FailingEmbeddings(),
        embedding_model="test-embedding",
        embedding_dimensions=None,
        max_file_bytes=100_000,
    )

    with pytest.raises(ProviderError, match="fake embedding service"):
        failing_sync.sync()

    assert store.document_digests()["docs/guide.md"] == previous_digest
    assert store.document_count() == 1


def test_corrupt_sqlite_index_is_reported_as_index_error(tmp_path: Path) -> None:
    database = tmp_path / "corrupt.sqlite3"
    database.write_bytes(b"not a SQLite database")

    with pytest.raises(IndexCorruptionError, match="Cannot open local index"):
        IndexStore(database)
