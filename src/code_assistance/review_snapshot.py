"""Materialize safe GitHub tree blobs for read-only indexing."""

import os
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from code_assistance.documents import _is_hard_excluded
from code_assistance.github_app import GitHubAppClient, GitHubAppError

MAX_SNAPSHOT_BYTES = 100_000_000
MAX_SNAPSHOT_FILES = 10_000
SNAPSHOT_FETCH_WORKERS = 6


@dataclass(frozen=True)
class SnapshotResult:
    root: Path
    included: frozenset[str]
    skipped: frozenset[str]


def _safe_relative(raw: str) -> Path | None:
    path = Path(raw)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {".", ".."} for part in path.parts)
        or any(ord(char) < 32 for char in raw)
        or _is_hard_excluded(path)
    ):
        return None
    return path


def materialize_snapshot(
    client: GitHubAppClient,
    repository: str,
    commit_sha: str,
    root: Path,
    max_file_bytes: int,
    *,
    markdown_only: bool,
    progress: Callable[[int, int], None] | None = None,
) -> SnapshotResult:
    tree_sha = client.commit_tree_sha(repository, commit_sha)
    entries = client.tree(repository, tree_sha)
    root.mkdir(parents=True, exist_ok=True)
    included: set[str] = set()
    skipped: set[str] = set()
    total_bytes = 0
    candidates: list[tuple[str, Path, str, int, bool]] = []

    def is_candidate(item: dict[str, object]) -> bool:
        raw = item.get("path")
        path = _safe_relative(raw) if isinstance(raw, str) else None
        if path is None or item.get("type") != "blob":
            return False
        if item.get("mode") not in {"100644", "100755"}:
            return False
        if path.name == ".gitignore":
            return True
        return (
            path.suffix == ".md"
            if markdown_only
            else path.suffix not in {".md", ".markdown", ".mdx"}
        )

    total_candidates = sum(is_candidate(item) for item in entries)
    for item in entries:
        raw = item.get("path")
        if not isinstance(raw, str):
            raise GitHubAppError("GitHub returned a tree entry without a path.")
        path = _safe_relative(raw)
        if path is None:
            skipped.add(raw)
            continue
        if item.get("type") != "blob" or item.get("mode") not in {"100644", "100755"}:
            skipped.add(raw)
            continue
        is_ignore_file = path.name == ".gitignore"
        if markdown_only:
            if path.suffix != ".md" and not is_ignore_file:
                continue
        elif path.suffix in {".md", ".markdown", ".mdx"} and not is_ignore_file:
            continue
        size = item.get("size")
        sha = item.get("sha")
        if not isinstance(size, int) or size < 0 or not isinstance(sha, str):
            raise GitHubAppError("GitHub returned an invalid tree entry.")
        if size > max_file_bytes:
            if is_ignore_file:
                raise GitHubAppError("A .gitignore file exceeds the snapshot limit.")
            skipped.add(raw)
            continue
        if len(candidates) >= MAX_SNAPSHOT_FILES or total_bytes + size > MAX_SNAPSHOT_BYTES:
            raise GitHubAppError("Repository snapshot exceeds the reviewer safety limit.")
        candidates.append((raw, path, sha, size, is_ignore_file))
        total_bytes += size

    if progress is not None:
        progress(0, total_candidates)
    processed = total_candidates - len(candidates)
    downloaded_bytes = 0
    with ThreadPoolExecutor(max_workers=SNAPSHOT_FETCH_WORKERS) as executor:
        futures = {
            executor.submit(client.blob, repository, sha, max_file_bytes): (
                raw,
                path,
                is_ignore_file,
            )
            for raw, path, sha, _size, is_ignore_file in candidates
        }
        for future in as_completed(futures):
            raw, path, is_ignore_file = futures[future]
            try:
                content = future.result()
                if len(content) > max_file_bytes:
                    raise GitHubAppError("GitHub returned a blob over the snapshot limit.")
                downloaded_bytes += len(content)
                if downloaded_bytes > MAX_SNAPSHOT_BYTES:
                    raise GitHubAppError("Repository snapshot exceeds the reviewer safety limit.")
                if b"\0" in content:
                    if is_ignore_file:
                        raise GitHubAppError("A .gitignore file is not valid text.")
                    skipped.add(raw)
                    continue
                try:
                    content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    if is_ignore_file:
                        raise GitHubAppError("A .gitignore file is not UTF-8 text.") from exc
                    skipped.add(raw)
                    continue
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                included.add(path.as_posix())
            finally:
                processed += 1
                if progress is not None and (processed % 25 == 0 or processed == total_candidates):
                    progress(processed, total_candidates)
    if not candidates and progress is not None:
        progress(total_candidates, total_candidates)

    # The existing collector uses `git check-ignore --no-index`. This temporary
    # repository contains only downloaded data and never executes its contents.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "LANG", "LC_ALL", "PATH", "TMP", "TEMP", "TMPDIR"}
    }
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_TEMPLATE_DIR": "/dev/null"})
    try:
        subprocess.run(
            ["git", "init", "--quiet", str(root)],
            check=True,
            capture_output=True,
            timeout=10,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise GitHubAppError("Cannot initialize the temporary repository snapshot.") from exc
    return SnapshotResult(root, frozenset(included), frozenset(skipped))
