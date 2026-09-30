from __future__ import annotations

from pathlib import Path

from copia.document_indexing.domain.errors import DocumentIndexingError
from copia.document_indexing.domain.models.source_document import SourceDocument


class DocumentLoader:
    """Loads supported text documents from one configured local directory."""

    SUPPORTED_SUFFIXES = {".md", ".txt"}

    def __init__(self, documents_path: Path) -> None:
        self._documents_path = documents_path.expanduser().resolve()

    @property
    def documents_path(self) -> Path:
        return self._documents_path

    def load(self) -> list[SourceDocument]:
        root = self._documents_path
        if not root.exists():
            return []
        if not root.is_dir():
            raise DocumentIndexingError("The configured documents path is not a directory")

        documents: list[SourceDocument] = []
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in self.SUPPORTED_SUFFIXES or not path.is_file():
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                continue
            try:
                content = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise DocumentIndexingError(
                    f"Unable to read source file: {path.relative_to(root).as_posix()}"
                ) from error
            if not content.strip():
                continue
            documents.append(
                SourceDocument(
                    source=path.relative_to(root).as_posix(),
                    title=path.stem,
                    suffix=path.suffix.lower(),
                    text=content,
                    size_bytes=resolved.stat().st_size,
                )
            )
        return documents

    def summary(self) -> tuple[int, int]:
        documents = self.load()
        return len(documents), sum(document.size_bytes for document in documents)
