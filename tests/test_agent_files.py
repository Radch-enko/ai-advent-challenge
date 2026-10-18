import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import code_assistance.agent_files as agent_files
from code_assistance.agent_files import AgentFileWorkspace, call_file_tool
from code_assistance.agent_service import prepare_agent_work
from code_assistance.cli import run_session
from code_assistance.config import load_config
from code_assistance.errors import AgentFileError, ProviderError
from tests.conftest import FakeEmbeddings


def update_patch(path: str, old: str, new: str) -> str:
    return f"*** Begin Patch\n*** Update File: {path}\n@@\n-{old}\n+{new}\n*** End Patch\n"


def configured_workspace(git_repository: Path, tmp_path: Path) -> AgentFileWorkspace:
    config_file = tmp_path / "agent-config.toml"
    config_file.write_text(
        "[agent.files]\n"
        'read_roots = ["src", "docs"]\n'
        'write_roots = ["src", "docs"]\n'
        'read_extensions = [".py", ".md"]\n'
        'write_extensions = [".py", ".md"]\n',
        encoding="utf-8",
    )
    return AgentFileWorkspace(git_repository, load_config(config_file))


def test_agent_searches_three_files_and_applies_reviewed_changes(
    git_repository: Path,
    tmp_path: Path,
) -> None:
    (git_repository / "src").mkdir()
    (git_repository / "docs").mkdir()
    (git_repository / "src" / "validator.py").write_text("def validate():\n    return True\n")
    (git_repository / "src" / "caller.py").write_text("from validator import validate\n")
    (git_repository / "docs" / "guide.md").write_text("Call validate.\n")
    workspace = configured_workspace(git_repository, tmp_path)

    matches = workspace.search_text("validate")["matches"]
    assert isinstance(matches, list)
    assert {match["path"] for match in matches} == {
        "src/validator.py",
        "src/caller.py",
        "docs/guide.md",
    }
    for name in ("src/validator.py", "src/caller.py", "docs/guide.md"):
        read = workspace.read_file(name)
        assert isinstance(read["content"], str)
        workspace.apply_patch(
            update_patch(name, read["content"].splitlines()[-1], "# updated"), str(read["sha256"])
        )
    workspace.apply_patch(
        "*** Begin Patch\n*** Add File: docs/changes.md\n"
        "+Validated usage changes.\n*** End Patch\n",
        None,
    )

    patch = workspace.diff()
    assert patch.count("--- a/") == 4
    assert workspace.apply() == [
        "docs/changes.md",
        "docs/guide.md",
        "src/caller.py",
        "src/validator.py",
    ]
    assert (git_repository / "docs" / "changes.md").read_text() == "Validated usage changes.\n"


def test_search_reaches_past_file_listing_limit(git_repository: Path, tmp_path: Path) -> None:
    source = git_repository / "src"
    source.mkdir()
    for index in range(201):
        (source / f"sample_{index:03}.py").write_text("unrelated\n")
    (source / "sample_201.py").write_text("unique API use\n")
    workspace = configured_workspace(git_repository, tmp_path)

    assert workspace.list_files()["truncated"] is True
    matches = workspace.search_text("unique API", "src")["matches"]
    assert matches == [{"path": "src/sample_201.py", "line": 1, "text": "unique API use"}]


def test_agent_denies_secrets_ignored_paths_and_symlinks(
    git_repository: Path,
    tmp_path: Path,
) -> None:
    (git_repository / "src").mkdir()
    (git_repository / "src" / "visible.py").write_text("public marker\n")
    (git_repository / "src" / "token.py").write_text("PRIVATE_TOKEN\n")
    (git_repository / "src" / "ignored.py").write_text("PRIVATE_IGNORED\n")
    (git_repository / "src" / ".env").write_text("PRIVATE_ENV\n")
    (git_repository / ".gitignore").write_text("src/ignored.py\n")
    outside = tmp_path / "outside.py"
    outside.write_text("PRIVATE_OUTSIDE\n")
    (git_repository / "src" / "linked.py").symlink_to(outside)
    workspace = configured_workspace(git_repository, tmp_path)

    assert workspace.list_files()["files"] == ["src/visible.py"]
    result = json.loads(call_file_tool(workspace, "read_file", {"path": "src/token.py"}))
    assert "error" in result
    for name in ("src/.env", "src/ignored.py", "src/linked.py", "../outside.py"):
        result = json.loads(call_file_tool(workspace, "read_file", {"path": name}))
        assert "error" in result
        assert "PRIVATE" not in json.dumps(result)
    assert workspace.search_text("PRIVATE")["matches"] == []

    observed: list[str] = []

    class SpyChat:
        def generate(self, instructions: str, prompt: str) -> str:
            return "unused"

        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Any,
            call_tool: Any,
            *,
            unbounded: bool = False,
        ) -> str:
            observed.extend([instructions, prompt])
            observed.append(call_tool("list_files", {}))
            observed.append(call_tool("search_text", {"query": "PRIVATE"}))
            observed.append(call_tool("read_file", {"path": "src/.env"}))
            return "No permitted matches."

    prepare_agent_work("Find the marker", git_repository, workspace.config, SpyChat())
    assert "PRIVATE_ENV" not in "".join(observed)
    assert "PRIVATE_TOKEN" not in "".join(observed)
    assert "PRIVATE_IGNORED" not in "".join(observed)
    assert "PRIVATE_OUTSIDE" not in "".join(observed)


def test_agent_rejects_unconfigured_access_and_stale_changes(
    git_repository: Path,
    tmp_path: Path,
) -> None:
    with pytest.raises(AgentFileError, match="allowlists"):
        AgentFileWorkspace(git_repository, load_config(tmp_path / "missing.toml"))
    (git_repository / "src").mkdir()
    file = git_repository / "src" / "code.py"
    file.write_text("before\n")
    workspace = configured_workspace(git_repository, tmp_path)
    digest = hashlib.sha256(b"before\n").hexdigest()
    workspace.apply_patch(update_patch("src/code.py", "before", "after"), digest)
    file.write_text("user edit\n")
    with pytest.raises(AgentFileError, match="changed"):
        workspace.apply()
    assert file.read_text() == "user edit\n"


def test_cli_requires_confirmation_and_handles_provider_failure(
    git_repository: Path,
    tmp_path: Path,
) -> None:
    (git_repository / "src").mkdir()
    target = git_repository / "src" / "sample.py"
    target.write_text("old\n")
    config = configured_workspace(git_repository, tmp_path).config
    output: list[str] = []

    class FakeChat:
        def generate(self, instructions: str, prompt: str) -> str:
            return "unused"

        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Any,
            call_tool: Any,
            *,
            unbounded: bool = False,
        ) -> str:
            read = json.loads(call_tool("read_file", {"path": "src/sample.py"}))
            call_tool(
                "apply_patch",
                {
                    "expected_sha256": read["sha256"],
                    "patch": update_patch("src/sample.py", "old", "new"),
                },
            )
            return "Prepared one file."

    answers = iter(["/agent update the sample", "n", "/exit"])
    run_session(
        git_repository,
        config,
        input_fn=lambda _: next(answers),
        output_fn=output.append,
        embedding_provider=FakeEmbeddings(),
        chat_generator=FakeChat(),
        index_directory=tmp_path / "indexes",
    )
    assert target.read_text() == "old\n"
    assert any("--- a/src/sample.py" in line for line in output)
    assert "Changes discarded." in output

    class FailingChat(FakeChat):
        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Any,
            call_tool: Any,
            *,
            unbounded: bool = False,
        ) -> str:
            raise ProviderError("Invented provider failure.")

    output.clear()
    answers = iter(["/agent update the sample", "/exit"])
    run_session(
        git_repository,
        config,
        input_fn=lambda _: next(answers),
        output_fn=output.append,
        embedding_provider=FakeEmbeddings(),
        chat_generator=FailingChat(),
        index_directory=tmp_path / "indexes",
    )
    assert target.read_text() == "old\n"
    assert "Error: Invented provider failure." in output


def test_cli_applies_after_explicit_confirmation(git_repository: Path, tmp_path: Path) -> None:
    (git_repository / "src").mkdir()
    target = git_repository / "src" / "sample.py"
    target.write_text("before\n")
    config = configured_workspace(git_repository, tmp_path).config
    output: list[str] = []

    class FakeChat:
        def generate(self, instructions: str, prompt: str) -> str:
            return "unused"

        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Any,
            call_tool: Any,
            *,
            unbounded: bool = False,
        ) -> str:
            read = json.loads(call_tool("read_file", {"path": "src/sample.py"}))
            call_tool(
                "apply_patch",
                {
                    "expected_sha256": read["sha256"],
                    "patch": update_patch("src/sample.py", "before", "after"),
                },
            )
            return "Prepared one file."

    answers = iter(["/agent update the sample", "y", "/exit"])
    run_session(
        git_repository,
        config,
        input_fn=lambda _: next(answers),
        output_fn=output.append,
        embedding_provider=FakeEmbeddings(),
        chat_generator=FakeChat(),
        index_directory=tmp_path / "indexes",
    )
    assert target.read_text() == "after\n"
    assert any("Applied changes to 1 file(s)" in line for line in output)
    assert any("Agent step 1: read src/sample.py." == line for line in output)
    assert any("Agent step 2: staged change to src/sample.py." == line for line in output)


def test_apply_reports_files_changed_before_write_failure(
    git_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (git_repository / "src").mkdir()
    first = git_repository / "src" / "a.py"
    second = git_repository / "src" / "b.py"
    first.write_text("old a\n")
    second.write_text("old b\n")
    workspace = configured_workspace(git_repository, tmp_path)
    for name in ("a.py", "b.py"):
        path = f"src/{name}"
        read = workspace.read_file(path)
        workspace.apply_patch(update_patch(path, f"old {name[0]}", "new"), str(read["sha256"]))
    real_replace = agent_files.os.replace
    calls = 0

    def fail_second_replace(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("invented disk failure")
        real_replace(*args, **kwargs)

    monkeypatch.setattr(agent_files.os, "replace", fail_second_replace)
    with pytest.raises(AgentFileError, match="src/a.py"):
        workspace.apply()
    assert first.read_text() == "new\n"
    assert second.read_text() == "old b\n"


def test_patch_updates_two_hunks_and_rejects_ambiguous_context(
    git_repository: Path, tmp_path: Path
) -> None:
    (git_repository / "src").mkdir()
    target = git_repository / "src" / "sample.py"
    target.write_text("first\nkeep\nlast\n", encoding="utf-8")
    workspace = configured_workspace(git_repository, tmp_path)
    digest = str(workspace.read_file("src/sample.py")["sha256"])
    patch = (
        "*** Begin Patch\n*** Update File: src/sample.py\n"
        "@@\n-first\n+changed first\n"
        "@@\n-last\n+changed last\n"
        "*** End Patch\n"
    )
    assert workspace.apply_patch(patch, digest)["staged"] is True
    assert target.read_text(encoding="utf-8") == "first\nkeep\nlast\n"
    assert workspace.read_file("src/sample.py")["content"] == "changed first\nkeep\nchanged last\n"

    target2 = git_repository / "src" / "duplicate.py"
    target2.write_text("same\nsame\n", encoding="utf-8")
    digest2 = str(workspace.read_file("src/duplicate.py")["sha256"])
    with pytest.raises(AgentFileError, match="ambiguous"):
        workspace.apply_patch(update_patch("src/duplicate.py", "same", "changed"), digest2)
    assert "src/duplicate.py" not in workspace.proposals


def test_patch_rejects_unsafe_path_and_stale_context(git_repository: Path, tmp_path: Path) -> None:
    (git_repository / "src").mkdir()
    target = git_repository / "src" / "sample.py"
    target.write_text("current\n", encoding="utf-8")
    workspace = configured_workspace(git_repository, tmp_path)
    digest = str(workspace.read_file("src/sample.py")["sha256"])
    with pytest.raises(AgentFileError, match="path policy"):
        workspace.apply_patch(update_patch("../escape.py", "old", "new"), None)
    with pytest.raises(AgentFileError, match="missing"):
        workspace.apply_patch(update_patch("src/sample.py", "old", "new"), digest)
    assert workspace.proposals == {}
    assert target.read_text(encoding="utf-8") == "current\n"
