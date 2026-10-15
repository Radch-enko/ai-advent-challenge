"""Read-only Git tools served over MCP stdio."""

import os
import subprocess
from pathlib import Path

from mcp.server import MCPServer

from code_assistance.documents import (
    HARD_EXCLUDED_COMPONENTS,
    SECRET_FILE_NAMES,
    SECRET_FILE_SUFFIXES,
)

SERVER = MCPServer("code-assistance-git")
GIT_TIMEOUT = 8
MAX_PATHS = 100
MAX_PATCH_BYTES = 16_384
MAX_COMMITS = 10


def _root(repo_path: str) -> Path:
    requested = Path(repo_path)
    if not requested.is_absolute():
        raise ValueError("repo_path must be an absolute repository path.")
    try:
        root = requested.resolve(strict=True)
        cwd = Path.cwd().resolve(strict=True)
    except OSError as exc:
        raise ValueError("The selected repository path is unavailable.") from exc
    if root != cwd:
        raise ValueError("repo_path must match the MCP server's selected repository.")
    result = _git(root, "rev-parse", "--show-toplevel")
    if Path(result.strip()).resolve() != root:
        raise ValueError("repo_path must be the Git repository root.")
    return root


def _git(root: Path, *args: str, limit: int = 65_536, truncate: bool = False) -> str:
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        in {"PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR"}
    }
    env.update(
        {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_OPTIONAL_LOCKS": "0"}
    )
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "-c", "core.fsmonitor=false", "-c", "diff.external=", *args],
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Git is unavailable or timed out.") from exc
    if result.returncode != 0:
        raise ValueError("Git could not read the selected repository.")
    if len(result.stdout) > limit and not truncate:
        raise ValueError("Git output exceeded the safety limit.")
    return result.stdout[:limit].decode("utf-8", errors="replace")


def _safe_path(root: Path, raw: str) -> bool:
    path = Path(raw)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or any(ord(character) < 32 for character in raw)
    ):
        return False
    components = {part.casefold() for part in path.parts}
    name = path.name.casefold()
    if components & HARD_EXCLUDED_COMPONENTS or name in SECRET_FILE_NAMES:
        return False
    if name.startswith(".env") or name.endswith(SECRET_FILE_SUFFIXES):
        return False
    if any(token in name for token in ("secret", "credential", "token", "password")):
        return False
    candidate = root / path
    if candidate.is_symlink():
        return False
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        return False
    return True


@SERVER.tool()
def get_current_branch(repo_path: str) -> dict[str, str | bool | None]:
    """Return the selected repository's branch, detached state and HEAD SHA."""
    root = _root(repo_path)
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD") if _has_branch(root) else None
    try:
        sha = _git(root, "rev-parse", "--verify", "HEAD").strip()
    except ValueError:
        sha = None
    return {
        "branch": branch.strip() if branch else None,
        "detached": branch is None,
        "commit_sha": sha,
    }


def _has_branch(root: Path) -> bool:
    try:
        _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except ValueError:
        return False
    return True


@SERVER.tool()
def get_status(repo_path: str) -> dict[str, object]:
    """Return bounded, filtered Git status entries without file contents."""
    root = _root(repo_path)
    output = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
    fields = output.split("\0")
    entries: list[dict[str, str]] = []
    index = 0
    truncated = False
    while index < len(fields) and fields[index]:
        field = fields[index]
        code, path = field[:2], field[3:]
        index += 1
        if code[0] in "RC" or code[1] in "RC":
            index += 1
        if _safe_path(root, path):
            if len(entries) == MAX_PATHS:
                truncated = True
                break
            entries.append({"path": path, "status": code})
    return {"entries": entries, "truncated": truncated}


@SERVER.tool()
def get_recent_commits(repo_path: str) -> dict[str, object]:
    """Return up to ten recent commit SHAs and subjects."""
    root = _root(repo_path)
    try:
        _git(root, "rev-parse", "--verify", "HEAD")
    except ValueError:
        return {"commits": []}
    output = _git(root, "log", f"-{MAX_COMMITS}", "--format=%H%x00%s%x00", limit=32_768)
    fields = output.split("\0")
    commits = []
    for index in range(0, len(fields) - 1, 2):
        sha = fields[index].strip()
        if len(sha) == 40 and all(char in "0123456789abcdef" for char in sha):
            commits.append({"sha": sha, "subject": fields[index + 1].strip()[:500]})
    return {"commits": commits}


@SERVER.tool()
def get_diff(repo_path: str) -> dict[str, object]:
    """Return bounded staged and unstaged tracked patches; omit untracked content."""
    root = _root(repo_path)
    files: list[dict[str, str]] = []
    remaining = MAX_PATCH_BYTES
    truncated = False
    for kind, extra in (("staged", ("--cached",)), ("unstaged", ())):
        names = _git(root, "diff", *extra, "--name-only", "-z", "--no-ext-diff", "--no-renames")
        for path in names.split("\0"):
            if not path or not _safe_path(root, path):
                continue
            if len(files) == MAX_PATHS or remaining <= 0:
                truncated = True
                break
            patch = _git(
                root,
                "diff",
                *extra,
                "--no-ext-diff",
                "--no-renames",
                "--no-textconv",
                "--",
                path,
                limit=remaining + 1,
                truncate=True,
            )
            encoded = patch.encode("utf-8")
            if len(encoded) > remaining:
                patch = encoded[:remaining].decode("utf-8", errors="ignore")
                truncated = True
            files.append({"path": path, "kind": kind, "patch": patch})
            remaining -= len(patch.encode("utf-8"))
        if truncated:
            break
    return {"files": files, "truncated": truncated}


def main() -> None:
    SERVER.run(transport="stdio")


if __name__ == "__main__":
    main()
