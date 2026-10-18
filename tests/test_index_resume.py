"""Interrupted reviews retain completed index batches and fetch blobs concurrently."""

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from code_assistance.errors import ProviderError
from code_assistance.index_store import IndexStore
from code_assistance.indexing import IndexSynchronizer
from code_assistance.review_snapshot import materialize_snapshot
from tests.conftest import FakeEmbeddings


def test_restart_embeds_only_files_after_the_last_completed_batch(
    git_repository: Path, tmp_path: Path
) -> None:
    for number in range(65):
        (git_repository / f"rule-{number:02}.md").write_text(
            f"Architecture rule {number}\n", encoding="utf-8"
        )
    store = IndexStore(tmp_path / "index.sqlite3")

    class FailAfterFirstBatch(FakeEmbeddings):
        def embed(
            self, texts: list[str] | tuple[str, ...], dimensions: int | None = None
        ) -> list[list[float]]:
            if self.calls:
                raise ProviderError("Temporary embedding failure.")
            return super().embed(texts, dimensions)

    first = IndexSynchronizer(
        git_repository,
        store,
        FailAfterFirstBatch(),
        "fixture-model",
        None,
        1000,
    )
    with pytest.raises(ProviderError, match="Temporary embedding failure"):
        first.sync()
    assert store.document_count() == 64

    resumed_embeddings = FakeEmbeddings()
    resumed = IndexSynchronizer(
        git_repository,
        store,
        resumed_embeddings,
        "fixture-model",
        None,
        1000,
    )
    result = resumed.sync()
    assert result.changed_document_count == 1
    assert store.document_count() == 65
    assert len(resumed_embeddings.calls) == 1
    assert resumed_embeddings.calls[0] == ["Architecture rule 64"]


def test_snapshot_fetches_independent_blobs_concurrently(tmp_path: Path) -> None:
    class FakeGitHub:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def commit_tree_sha(self, repository: str, commit_sha: str) -> str:
            return commit_sha

        def tree(self, repository: str, ref: str) -> list[dict[str, Any]]:
            return [
                {
                    "path": f"src/file-{number:02}.py",
                    "type": "blob",
                    "mode": "100644",
                    "size": 2,
                    "sha": str(number),
                }
                for number in range(12)
            ]

        def blob(self, repository: str, sha: str, max_bytes: int) -> bytes:
            with self.lock:
                self.active += 1
                self.max_active = max(self.active, self.max_active)
            time.sleep(0.02)
            with self.lock:
                self.active -= 1
            return b"x\n"

    github = FakeGitHub()
    events: list[tuple[int, int]] = []
    result = materialize_snapshot(
        github,  # type: ignore[arg-type]
        "owner/repo",
        "a" * 40,
        tmp_path / "snapshot",
        1000,
        markdown_only=False,
        progress=lambda done, total: events.append((done, total)),
    )
    assert len(result.included) == 12
    assert github.max_active > 1
    assert events[-1] == (12, 12)
