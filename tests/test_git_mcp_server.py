import subprocess
import sys
from pathlib import Path

import pytest

from code_assistance.config import load_config
from code_assistance.errors import GitUnavailableError
from code_assistance.git_mcp_server import MAX_PATCH_BYTES
from code_assistance.mcp_client import MCPBranchProvider
from code_assistance.models import BranchContext


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _client(repo: Path, tmp_path: Path) -> MCPBranchProvider:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[git_mcp]\ncommand = ["{sys.executable}", "-m", "code_assistance.git_mcp_server"]\n',
        encoding="utf-8",
    )
    return MCPBranchProvider(load_config(config_path))


def test_stdio_tools_read_branch_status_history_and_diff(
    git_repository: Path, tmp_path: Path
) -> None:
    repo = git_repository
    client = _client(repo, tmp_path)
    branch = client.current_branch(repo)
    assert branch.branch is not None
    assert branch.commit_sha is None

    (repo / "README.md").write_text("Invented manual.\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "Add invented manual")
    (repo / "README.md").write_text("Invented manual.\nA new line.\n", encoding="utf-8")
    (repo / "notes.txt").write_text("fixture", encoding="utf-8")
    (repo / ".env").write_text("DO_NOT_SEND=fixture", encoding="utf-8")

    assert "README.md" in " ".join(item.text for item in client.status(repo))
    assert "notes.txt" in " ".join(item.text for item in client.status(repo))
    assert ".env" not in " ".join(item.text for item in client.status(repo))
    assert "Add invented manual" in client.recent_commits(repo)[0].text
    assert "A new line" in client.diff(repo)[0].text
    assert "notes.txt" not in " ".join(item.text for item in client.diff(repo))

    _git(repo, "add", "README.md")
    assert any("staged diff" in item.reference for item in client.diff(repo))

    _git(repo, "checkout", "-b", "fixture/next")
    assert client.current_branch(repo).branch == "fixture/next"

    _git(repo, "checkout", "--detach", "HEAD")
    detached = client.current_branch(repo)
    assert detached == BranchContext(None, True, _git(repo, "rev-parse", "HEAD"))


def test_diff_is_bounded_and_rejects_wrong_repository(git_repository: Path, tmp_path: Path) -> None:
    repo = git_repository
    (repo / "data.txt").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "data.txt")
    _git(repo, "commit", "-m", "Initial fixture")
    (repo / "data.txt").write_text("initial\n" + "x" * (MAX_PATCH_BYTES * 2), encoding="utf-8")
    client = _client(repo, tmp_path)

    evidence = client.diff(repo)
    assert any("truncated" in item.text for item in evidence)
    assert sum(len(item.text.encode("utf-8")) for item in evidence) < MAX_PATCH_BYTES + 500

    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(GitUnavailableError):
        client.status(other)


def test_secret_paths_and_outside_symlinks_are_not_exposed(
    git_repository: Path, tmp_path: Path
) -> None:
    repo = git_repository
    (repo / ".env").write_text("INVENTED_SECRET=fixture\n", encoding="utf-8")
    (repo / "visible.txt").write_text("visible\n", encoding="utf-8")
    _git(repo, "add", ".env", "visible.txt")
    _git(repo, "commit", "-m", "Fixture files")
    (repo / ".env").write_text("INVENTED_SECRET=changed\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside fixture", encoding="utf-8")
    (repo / "outside-link").symlink_to(outside)
    client = _client(repo, tmp_path)

    assert ".env" not in " ".join(item.text for item in client.status(repo))
    assert "outside-link" not in " ".join(item.text for item in client.status(repo))
    assert "INVENTED_SECRET" not in " ".join(item.text for item in client.diff(repo))
