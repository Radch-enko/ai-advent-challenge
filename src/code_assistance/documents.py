import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from code_assistance.errors import DocumentError, UnsafePathError
from code_assistance.models import Document

HARD_EXCLUDED_COMPONENTS = frozenset(
    {
        ".cache",
        ".aws",
        ".env",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ssh",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "credentials",
        "dist",
        "env",
        "keys",
        "node_modules",
        "private_keys",
        "secrets",
        "site-packages",
        "target",
        "vendor",
        "venv",
        "virtualenv",
    }
)
SECRET_FILE_SUFFIXES = (".pem", ".key")
SECRET_FILE_NAMES = frozenset({"id_rsa", "id_ed25519", "credentials.md", "secrets.md"})
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
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DocumentError("A documentation file could not be resolved.") from exc
    if not resolved.is_relative_to(root):
        raise UnsafePathError("A documentation path resolves outside the selected repository.")
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
    parts = {part.casefold() for part in relative_path.parts}
    name = relative_path.name.casefold()
    return (
        bool(parts.intersection(HARD_EXCLUDED_COMPONENTS))
        or name.startswith(".env")
        or "credential" in name
        or "secret" in name
        or name in SECRET_FILE_NAMES
        or name.endswith(SECRET_FILE_SUFFIXES)
    )


def _candidate_paths(repository_root: Path) -> list[Path]:
    candidates: list[Path] = []
    try:
        for entry in repository_root.iterdir():
            if entry.name.casefold().startswith("readme") and (
                entry.is_file() or entry.is_symlink()
            ):
                candidates.append(entry)
    except OSError as exc:
        raise DocumentError("The repository root could not be scanned.") from exc

    docs_root = repository_root / "docs"
    if docs_root.is_dir() and not docs_root.is_symlink():
        for current, directory_names, file_names in os.walk(docs_root, followlinks=False):
            current_path = Path(current)
            directory_names[:] = [
                name
                for name in directory_names
                if name.casefold() not in HARD_EXCLUDED_COMPONENTS
                and not (current_path / name).is_symlink()
            ]
            for name in file_names:
                candidate = current_path / name
                if candidate.suffix.casefold() in {".md", ".markdown"}:
                    candidates.append(candidate)

    selected: list[Path] = []
    for candidate in candidates:
        try:
            relative = candidate.relative_to(repository_root)
        except ValueError:
            continue
        if not _is_hard_excluded(relative):
            selected.append(candidate)
    return sorted(set(selected), key=lambda path: path.relative_to(repository_root).as_posix())


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
