"""Index progress reports completed files across embedding batches and cache reuse."""

from pathlib import Path

from code_assistance.index_store import IndexStore
from code_assistance.indexing import IndexSynchronizer
from tests.conftest import FakeEmbeddings


def test_index_progress_counts_files_across_batches(git_repository: Path, tmp_path: Path) -> None:
    for number in range(65):
        (git_repository / f"rule-{number:02}.md").write_text(
            f"Architecture rule {number}\n", encoding="utf-8"
        )
    embeddings = FakeEmbeddings()
    events: list[tuple[int, int]] = []
    synchronizer = IndexSynchronizer(
        repository_root=git_repository,
        store=IndexStore(tmp_path / "index.sqlite3"),
        embedding_provider=embeddings,
        embedding_model="fixture-model",
        embedding_dimensions=None,
        max_file_bytes=1000,
        progress=lambda done, total: events.append((done, total)),
    )

    synchronizer.sync()

    assert events[0] == (0, 65)
    assert (64, 65) in events
    assert events[-1] == (65, 65)
    assert len(embeddings.calls) == 2

    events.clear()
    synchronizer.sync()
    assert events == [(65, 65), (65, 65)]
    assert len(embeddings.calls) == 2
