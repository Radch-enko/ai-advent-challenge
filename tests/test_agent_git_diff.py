import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from code_assistance.agent_service import prepare_agent_work
from code_assistance.config import load_config
from code_assistance.mcp_client import MCPBranchProvider


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
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
        check=True,
        capture_output=True,
    )


def test_agent_gets_only_permitted_current_diff_through_mcp(
    git_repository: Path, tmp_path: Path
) -> None:
    repo = git_repository
    (repo / "src").mkdir()
    (repo / "docs").mkdir()
    (repo / "src" / "sample.py").write_text("old\n", encoding="utf-8")
    (repo / "docs" / "private.md").write_text("old\n", encoding="utf-8")
    (repo / ".env").write_text("OLD_SECRET\n", encoding="utf-8")
    _git(repo, "add", "src/sample.py", "docs/private.md", ".env")
    _git(repo, "commit", "-m", "Invented initial files")
    (repo / "src" / "sample.py").write_text("staged\n", encoding="utf-8")
    (repo / "docs" / "private.md").write_text("PRIVATE_DOC\n", encoding="utf-8")
    (repo / ".env").write_text("PRIVATE_SECRET\n", encoding="utf-8")
    _git(repo, "add", "src/sample.py", "docs/private.md", ".env")
    (repo / "src" / "sample.py").write_text("unstaged\n", encoding="utf-8")

    config_file = tmp_path / "agent.toml"
    config_file.write_text(
        "[agent.files]\n"
        'read_roots = ["src"]\n'
        'write_roots = ["src"]\n'
        'read_extensions = [".py"]\n'
        'write_extensions = [".py"]\n'
        "[git_mcp]\n"
        f'command = ["{sys.executable}", "-m", "code_assistance.git_mcp_server"]\n',
        encoding="utf-8",
    )
    config = load_config(config_file)
    seen: list[str] = []

    class FakeChat:
        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Any,
            call_tool: Any,
            *,
            unbounded: bool = False,
        ) -> str:
            del instructions, prompt
            assert unbounded
            assert "get_diff" in {tool.name for tool in tools}
            seen.append(call_tool("get_diff", {}))
            assert "error" in json.loads(call_tool("get_diff", {"path": ".env"}))
            return "Inspected current changes."

    status: list[str] = []
    summary, workspace = prepare_agent_work(
        "Inspect current changes",
        repo,
        config,
        FakeChat(),
        status=status.append,
        git_provider=MCPBranchProvider(config),
    )
    data = json.loads(seen[0])
    assert summary == "Inspected current changes."
    assert [(item["path"], item["kind"]) for item in data["files"]] == [
        ("src/sample.py", "staged"),
        ("src/sample.py", "unstaged"),
    ]
    assert "staged" in seen[0] and "unstaged" in seen[0]
    assert "PRIVATE_DOC" not in seen[0]
    assert "PRIVATE_SECRET" not in seen[0]
    assert workspace.diff() == ""
    assert any("found 2 permitted diff(s)" in line for line in status)
    assert all(".env" not in line for line in status)
