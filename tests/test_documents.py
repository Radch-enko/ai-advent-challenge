from pathlib import Path

import pytest

from code_assistance.documents import collect_documents, read_document
from code_assistance.errors import UnsafePathError


def test_collection_reads_readme_and_docs_markdown_and_honors_gitignore(
    git_repository: Path,
) -> None:
    (git_repository / "README.md").write_text("Invented overview.", encoding="utf-8")
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("Invented guide.", encoding="utf-8")
    (docs / "ignored.md").write_text("Do not index this.", encoding="utf-8")
    (docs / "secrets.md").write_text("Do not index this either.", encoding="utf-8")
    (docs / "api.yaml").write_text("openapi: 3.1.0", encoding="utf-8")
    (git_repository / ".gitignore").write_text("docs/ignored.md\n", encoding="utf-8")

    collection = collect_documents(git_repository, max_bytes=1_000)

    assert {document.path for document in collection.documents} == {
        "README.md",
        "docs/guide.md",
    }
    assert all("Do not index" not in document.text for document in collection.documents)


def test_read_document_rejects_path_outside_repository(
    git_repository: Path,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("Invented external content.", encoding="utf-8")

    with pytest.raises(UnsafePathError):
        read_document(git_repository, outside, max_bytes=1_000)


def test_read_document_rejects_symlink_escape(
    git_repository: Path,
    tmp_path: Path,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("Invented external content.", encoding="utf-8")
    link = docs / "external.md"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable: {exc}")

    with pytest.raises(UnsafePathError):
        read_document(git_repository, link, max_bytes=1_000)

    collection = collect_documents(git_repository, max_bytes=1_000)
    assert not collection.documents
    assert any("outside the repository" in warning for warning in collection.warnings)


def test_oversized_and_binary_documents_are_skipped(git_repository: Path) -> None:
    (git_repository / "README.md").write_bytes(b"\xff\x00binary")
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "large.md").write_text("x" * 100, encoding="utf-8")

    collection = collect_documents(git_repository, max_bytes=20)

    assert not collection.documents
    assert len(collection.warnings) == 2
