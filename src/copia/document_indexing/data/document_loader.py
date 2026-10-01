from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

from copia.document_indexing.domain.errors import DocumentIndexingError
from copia.document_indexing.domain.models.source_document import SourceDocument


@dataclass(frozen=True)
class _IgnoreRule:
    directory: Path
    pattern_parts: tuple[str, ...]


class DocumentLoader:
    """Loads supported Markdown documents from one configured local directory."""

    SUPPORTED_SUFFIXES = {".md"}

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
        self._load_directory(root, (), documents)
        return documents

    def summary(self) -> tuple[int, int]:
        documents = self.load()
        return len(documents), sum(document.size_bytes for document in documents)

    def _load_directory(
        self,
        directory: Path,
        inherited_rules: tuple[_IgnoreRule, ...],
        documents: list[SourceDocument],
    ) -> None:
        rules = inherited_rules + self._read_ignore_rules(directory)
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as error:
            relative = self._relative_path(directory)
            raise DocumentIndexingError(f"Unable to read source directory: {relative}") from error

        for path in children:
            if path.name == ".ignore":
                continue
            if path.is_dir() and not path.is_symlink():
                if not self._is_ignored(path, rules):
                    self._load_directory(path, rules, documents)
                continue
            if path.suffix.lower() not in self.SUPPORTED_SUFFIXES or not path.is_file():
                continue
            if self._is_ignored(path, rules):
                continue

            resolved = path.resolve()
            if not resolved.is_relative_to(self._documents_path):
                continue
            try:
                content = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise DocumentIndexingError(
                    f"Unable to read source file: {self._relative_path(path)}"
                ) from error
            if not content.strip():
                continue
            documents.append(
                SourceDocument(
                    source=self._relative_path(path),
                    title=path.stem,
                    suffix=path.suffix.lower(),
                    text=content,
                    size_bytes=resolved.stat().st_size,
                )
            )

    def _read_ignore_rules(self, directory: Path) -> tuple[_IgnoreRule, ...]:
        ignore_path = directory / ".ignore"
        if not ignore_path.exists():
            return ()
        if ignore_path.is_symlink() and not ignore_path.resolve().is_relative_to(
            self._documents_path
        ):
            raise DocumentIndexingError(
                f"Unable to read ignore rules: {self._relative_path(ignore_path)}"
            )
        try:
            lines = ignore_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise DocumentIndexingError(
                f"Unable to read ignore rules: {self._relative_path(ignore_path)}"
            ) from error

        rules: list[_IgnoreRule] = []
        for line_number, line in enumerate(lines, start=1):
            pattern = line.strip()
            if not pattern or pattern.startswith("#"):
                continue
            if pattern.startswith("!"):
                raise DocumentIndexingError(
                    f"Negation is not supported in {self._relative_path(ignore_path)}:{line_number}"
                )
            pattern = pattern.rstrip("/")
            pattern_parts = tuple(pattern.split("/"))
            if (
                not pattern
                or pattern.startswith("/")
                or any(part in {"", ".", ".."} for part in pattern_parts)
            ):
                raise DocumentIndexingError(
                    f"Invalid ignore pattern in {self._relative_path(ignore_path)}:{line_number}"
                )
            rules.append(_IgnoreRule(directory=directory, pattern_parts=pattern_parts))
        return tuple(rules)

    def _is_ignored(self, path: Path, rules: tuple[_IgnoreRule, ...]) -> bool:
        for rule in rules:
            relative_parts = path.relative_to(rule.directory).parts
            if self._glob_matches(rule.pattern_parts, relative_parts):
                return True
        return False

    @staticmethod
    def _glob_matches(pattern_parts: tuple[str, ...], path_parts: tuple[str, ...]) -> bool:
        @cache
        def matches(pattern_index: int, path_index: int) -> bool:
            if pattern_index == len(pattern_parts):
                return path_index == len(path_parts)
            pattern_part = pattern_parts[pattern_index]
            if pattern_part == "**":
                return matches(pattern_index + 1, path_index) or (
                    path_index < len(path_parts) and matches(pattern_index, path_index + 1)
                )
            if path_index == len(path_parts):
                return False
            return DocumentLoader._segment_matches(
                pattern_part, path_parts[path_index]
            ) and matches(pattern_index + 1, path_index + 1)

        return matches(0, 0)

    @staticmethod
    @lru_cache(maxsize=256)
    def _segment_regex(pattern: str) -> re.Pattern[str]:
        expression = "".join(
            ".*" if character == "*" else re.escape(character) for character in pattern
        )
        return re.compile(f"^{expression}$")

    @staticmethod
    def _segment_matches(pattern: str, value: str) -> bool:
        return DocumentLoader._segment_regex(pattern).fullmatch(value) is not None

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self._documents_path).as_posix() or "."
