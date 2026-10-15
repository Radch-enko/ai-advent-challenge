import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from code_assistance.cli import run_session
from code_assistance.config import load_config
from code_assistance.errors import BranchUnavailableError, ConfigurationError, RepositoryError
from code_assistance.mcp_client import MCPBranchProvider
from code_assistance.models import BranchContext
from code_assistance.repository import find_repository_root
from tests.conftest import FakeEmbeddings


def test_repository_discovery_works_from_nested_directory(git_repository: Path) -> None:
    nested = git_repository / "a" / "b"
    nested.mkdir(parents=True)

    assert find_repository_root(nested) == git_repository.resolve()


def test_repository_discovery_rejects_non_repository(tmp_path: Path) -> None:
    with pytest.raises(RepositoryError, match="No Git repository"):
        find_repository_root(tmp_path)


def test_mcp_config_rejects_shell_command_string(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[git_mcp]\ncommand = "git status"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="array of executable and arguments"):
        load_config(config_file)


def test_mcp_client_calls_configured_tool_and_does_not_pass_openai_key(
    git_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[git_mcp]\ncommand = ["/usr/bin/example-mcp", "--stdio"]\n',
        encoding="utf-8",
    )
    config = load_config(config_file)
    monkeypatch.setenv("OPENAI_API_KEY", "never-forward-this")
    observations: dict[str, Any] = {}

    class FakeParameters:
        def __init__(
            self,
            command: str,
            args: list[str],
            env: dict[str, str],
            cwd: Path,
        ) -> None:
            observations["command"] = command
            observations["args"] = args
            observations["env"] = env
            observations["cwd"] = cwd

    class FakeClient:
        def __init__(self, parameters: FakeParameters) -> None:
            observations["parameters"] = parameters

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def call_tool(self, name: str, arguments: dict[str, str]) -> object:
            observations["tool"] = name
            observations["arguments"] = arguments
            return SimpleNamespace(
                is_error=False,
                structured_content={
                    "branch": "fixture/main",
                    "detached": False,
                    "commit_sha": "0123456789abcdef",
                },
            )

    monkeypatch.setattr("code_assistance.mcp_client.StdioServerParameters", FakeParameters)
    monkeypatch.setattr("code_assistance.mcp_client.Client", FakeClient)

    result = MCPBranchProvider(config).current_branch(git_repository)

    assert result == BranchContext("fixture/main", False, "0123456789abcdef")
    assert observations["command"] == "/usr/bin/example-mcp"
    assert observations["args"] == ["--stdio"]
    assert observations["tool"] == "get_current_branch"
    assert observations["arguments"] == {"repo_path": str(git_repository.resolve())}
    assert observations["cwd"] == git_repository
    assert "OPENAI_API_KEY" not in observations["env"]


def test_mcp_tool_result_requires_structured_branch_data() -> None:
    with pytest.raises(BranchUnavailableError):
        MCPBranchProvider._parse_result({"branch": None, "detached": True, "commit_sha": None})


def test_mcp_client_talks_to_a_real_stdio_server(
    git_repository: Path,
    tmp_path: Path,
) -> None:
    server_script = tmp_path / "branch_server.py"
    server_script.write_text(
        textwrap.dedent(
            """
            from mcp.server import MCPServer

            server = MCPServer("fixture-git")

            @server.tool()
            def get_current_branch(repo_path: str) -> dict[str, object]:
                return {
                    "branch": "integration/main",
                    "detached": False,
                    "commit_sha": "0123456789abcdef",
                }

            if __name__ == "__main__":
                server.run()
            """
        ),
        encoding="utf-8",
    )
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f'[git_mcp]\ncommand = ["{sys.executable}", "{server_script}"]\n',
        encoding="utf-8",
    )

    result = MCPBranchProvider(load_config(config_file)).current_branch(git_repository)

    assert result == BranchContext("integration/main", False, "0123456789abcdef")


def test_startup_warning_precedes_embedding_request(
    git_repository: Path,
    tmp_path: Path,
) -> None:
    (git_repository / "README.md").write_text("Invented project layout.", encoding="utf-8")
    config = load_config(tmp_path / "config.toml")
    output_events: list[str] = []
    event_log: list[str] = []

    class RecordingEmbeddings(FakeEmbeddings):
        def embed(
            self,
            texts: list[str] | tuple[str, ...],
            dimensions: int | None = None,
        ) -> list[list[float]]:
            event_log.append("embedding")
            return super().embed(texts, dimensions)

    run_session(
        repository_root=git_repository,
        config=config,
        input_fn=lambda prompt: "/exit",
        output_fn=lambda message: (output_events.append(message), event_log.append(message)),
        embedding_provider=RecordingEmbeddings(),
        index_directory=tmp_path / "indexes",
    )

    privacy_index = next(
        index for index, event in enumerate(event_log) if event.startswith("Privacy notice:")
    )
    embedding_index = event_log.index("embedding")
    assert privacy_index < embedding_index
