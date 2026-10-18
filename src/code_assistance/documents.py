import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from code_assistance.errors import DocumentError, UnsafePathError
from code_assistance.file_policy import is_hard_excluded
from code_assistance.models import Document

IGNORE_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class DocumentCollection:
    documents: tuple[Document, ...]
    warnings: tuple[str, ...]


def read_document(repository_root: Path, source_path: Path, max_bytes: int) -> Document:
    root = repository_root.resolve(strict=True)
    candidate = source_path if source_path.is_absolute() else root / source_path
    lexical_candidate = Path(os.path.abspath(candidate))
    if not lexical_candidate.is_relative_to(root):
        raise UnsafePathError("A documentation path escapes the selected repository.")
    if is_hard_excluded(lexical_candidate.relative_to(root)):
        raise UnsafePathError("A documentation path is excluded.")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DocumentError("A documentation file could not be resolved.") from exc
    if not resolved.is_relative_to(root):
        raise UnsafePathError("A documentation path resolves outside the selected repository.")
    if is_hard_excluded(resolved.relative_to(root)):
        raise UnsafePathError("A documentation path is excluded.")
    if not resolved.is_file():
        raise DocumentError("A documentation path is not a regular file.")

    try:
        if resolved.stat().st_size > max_bytes:
            raise DocumentError(f"Documentation file exceeds the {max_bytes}-byte limit.")
        with resolved.open("rb") as source:
            content = source.read(max_bytes + 1)
    except OSError as exc:
        raise DocumentError("A documentation file could not be read.") from exc
    if len(content) > max_bytes:
        raise DocumentError(f"Documentation file exceeds the {max_bytes}-byte limit.")
    if b"\0" in content:
        raise DocumentError("Binary files are not supported as documentation.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentError("Documentation must be UTF-8 text.") from exc

    return Document(
        path=lexical_candidate.relative_to(root).as_posix(),
        text=text,
        digest=hashlib.sha256(content).hexdigest(),
    )


def _is_hard_excluded(relative_path: Path) -> bool:
    return is_hard_excluded(relative_path)


def _candidate_paths(repository_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for current, directory_names, file_names in os.walk(repository_root, followlinks=False):
        current_path = Path(current)
        directory_names[:] = [
            name
            for name in directory_names
            if not is_hard_excluded(Path(name)) and not (current_path / name).is_symlink()
        ]
        for name in file_names:
            if Path(name).suffix == ".md":
                candidates.append(current_path / name)

    selected: list[Path] = []
    for candidate in candidates:
        try:
            relative = candidate.relative_to(repository_root)
        except ValueError:
            continue
        if not _is_hard_excluded(relative):
            selected.append(candidate)
    return sorted(set(selected), key=lambda path: path.relative_to(repository_root).as_posix())


def collect_code_files(repository_root: Path, max_bytes: int) -> DocumentCollection:
    """Collect safe text files other than Markdown from a repository snapshot."""
    root = repository_root.resolve(strict=True)
    candidates: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directory_names[:] = [
            name
            for name in directory_names
            if not is_hard_excluded(Path(name)) and not (current_path / name).is_symlink()
        ]
        for name in file_names:
            candidate = current_path / name
            relative = candidate.relative_to(root)
            if (
                candidate.is_symlink()
                or relative.suffix in {".md", ".markdown", ".mdx"}
                or _is_hard_excluded(relative)
            ):
                continue
            candidates.append(candidate)
    ignored = _ignored_paths(root, candidates)
    documents: list[Document] = []
    warnings: list[str] = []
    for candidate in sorted(candidates):
        relative_name = candidate.relative_to(root).as_posix()
        if relative_name in ignored:
            continue
        try:
            documents.append(read_document(root, candidate, max_bytes))
        except DocumentError as exc:
            warnings.append(f"Skipped {relative_name}: {exc}")
    return DocumentCollection(tuple(documents), tuple(warnings))


def _ignored_paths(repository_root: Path, candidates: list[Path]) -> set[str]:
    relative_paths = [path.relative_to(repository_root).as_posix() for path in candidates]
    if not relative_paths:
        return set()
    payload = b"\0".join(os.fsencode(path) for path in relative_paths) + b"\0"
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "check-ignore",
                "--no-index",
                "--stdin",
                "-z",
            ],
            check=False,
            input=payload,
            capture_output=True,
            timeout=IGNORE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise DocumentError("Git is required to respect repository ignore rules.") from exc
    except subprocess.TimeoutExpired as exc:
        raise DocumentError("Checking repository ignore rules timed out.") from exc

    if result.returncode not in {0, 1}:
        raise DocumentError("Git could not determine which documentation files are ignored.")
    return {os.fsdecode(path) for path in result.stdout.split(b"\0") if path}


def collect_documents(repository_root: Path, max_bytes: int) -> DocumentCollection:
    root = repository_root.resolve(strict=True)
    candidates = _candidate_paths(root)
    ignored = _ignored_paths(root, candidates)
    documents: list[Document] = []
    warnings: list[str] = []

    for candidate in candidates:
        relative_path = candidate.relative_to(root).as_posix()
        if relative_path in ignored:
            continue
        try:
            documents.append(read_document(root, candidate, max_bytes))
        except UnsafePathError:
            warnings.append(
                f"Skipped documentation path that resolves outside the repository: {relative_path}"
            )
        except DocumentError as exc:
            warnings.append(f"Skipped {relative_path}: {exc}")

    return DocumentCollection(tuple(documents), tuple(warnings))
