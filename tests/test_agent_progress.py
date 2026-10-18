import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from code_assistance.agent_service import prepare_agent_work
from code_assistance.config import load_config
from code_assistance.errors import ProviderError
from code_assistance.models import ToolDefinition
from code_assistance.providers import OpenAIProvider


def test_provider_continues_past_previous_round_and_call_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = OpenAIProvider(load_config(tmp_path / "missing.toml"))
    requests = 0
    calls: list[str] = []

    class FakeResponses:
        def create(self, **kwargs: object) -> SimpleNamespace:
            nonlocal requests
            del kwargs
            requests += 1
            if requests <= 20:
                call = SimpleNamespace(
                    type="function_call", name="inspect", arguments="{}", call_id=str(requests)
                )
                return SimpleNamespace(output=[call], output_text="")
            return SimpleNamespace(output=[], output_text="Finished after repeated inspection.")

    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(responses=FakeResponses()))
    result = provider.generate_with_tools(
        "Invented instructions",
        "Invented question",
        [ToolDefinition("inspect", "Inspect fixture data", {"type": "object", "properties": {}})],
        lambda name, arguments: calls.append(name) or json.dumps(arguments),
        unbounded=True,
    )

    assert result == "Finished after repeated inspection."
    assert requests == 21
    assert calls == ["inspect"] * 20


def test_provider_preserves_bounded_tool_loop_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = OpenAIProvider(load_config(tmp_path / "missing.toml"))
    requests = 0

    class FakeResponses:
        def create(self, **kwargs: object) -> SimpleNamespace:
            nonlocal requests
            del kwargs
            requests += 1
            call = SimpleNamespace(
                type="function_call", name="inspect", arguments="{}", call_id=str(requests)
            )
            return SimpleNamespace(output=[call], output_text="")

    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(responses=FakeResponses()))
    with pytest.raises(ProviderError, match="allowed tool rounds"):
        provider.generate_with_tools(
            "Invented instructions",
            "Invented question",
            [
                ToolDefinition(
                    "inspect", "Inspect fixture data", {"type": "object", "properties": {}}
                )
            ],
            lambda name, arguments: json.dumps(arguments),
        )
    assert requests == 8


def test_agent_reports_actions_without_logging_contents_or_denied_paths(
    git_repository: Path, tmp_path: Path
) -> None:
    source = git_repository / "src"
    source.mkdir()
    target = source / "sample.py"
    target.write_text("invented code\n")
    (source / ".env").write_text("fixture secret value\n")
    config_file = tmp_path / "agent.toml"
    config_file.write_text(
        "[agent.files]\n"
        'read_roots = ["src"]\n'
        'write_roots = ["src"]\n'
        'read_extensions = [".py"]\n'
        'write_extensions = [".py"]\n'
    )
    status: list[str] = []

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
            assert unbounded
            del instructions, prompt, tools
            call_tool("list_files", {})
            call_tool("search_text", {"query": "invented code"})
            call_tool("read_file", {"path": "src/.env"})
            call_tool("read_file\nlog injection", {"path": "src/sample.py"})
            read = json.loads(call_tool("read_file", {"path": "src/sample.py"}))
            call_tool(
                "apply_patch",
                {
                    "expected_sha256": read["sha256"],
                    "patch": "*** Begin Patch\n*** Update File: src/sample.py\n"
                    "@@\n-invented code\n+updated code\n*** End Patch\n",
                },
            )
            return "Prepared a change."

    summary, workspace = prepare_agent_work(
        "Update the sample", git_repository, load_config(config_file), FakeChat(), status.append
    )

    assert summary == "Prepared a change."
    assert "updated code" in workspace.diff()
    assert target.read_text() == "invented code\n"
    assert any("Agent step 1: listed 1 file(s)." == line for line in status)
    assert any("Agent step 2: found 1 match(es)." == line for line in status)
    assert any("Agent step 3: read_file denied" in line for line in status)
    assert any("Agent step 4: unknown tool denied" in line for line in status)
    assert any("Agent step 6: staged change to src/sample.py." == line for line in status)
    assert status[-1] == "Agent: finished after 6 file action(s)."
    assert all(".env" not in line for line in status)
    assert all("log injection" not in line for line in status)
    assert all("fixture secret value" not in line for line in status)
    assert all("invented code" not in line for line in status)
