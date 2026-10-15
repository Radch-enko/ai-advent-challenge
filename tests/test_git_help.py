from collections.abc import Callable, Sequence
from pathlib import Path

from code_assistance.cli import run_session
from code_assistance.config import load_config
from code_assistance.index_store import IndexStore
from code_assistance.indexing import IndexSynchronizer, index_database_path
from code_assistance.models import BranchContext, GitEvidence, ToolDefinition
from code_assistance.service import HelpService
from tests.conftest import FakeEmbeddings


class FakeChat:
    def __init__(self, response: str, selected_tool: str | None = None) -> None:
        self.response = response
        self.selected_tool = selected_tool
        self.prompts: list[str] = []
        self.tool_outputs: list[str] = []
        self.schemas: list[list[str]] = []

    def generate(self, instructions: str, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        self.prompts.append(prompt)
        self.schemas.append([tool.name for tool in tools])
        if self.selected_tool:
            self.tool_outputs.append(call_tool(self.selected_tool, {}))
        return self.response


class FakeGit:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def available_tools(self, repository_root: Path) -> list[ToolDefinition]:
        return [
            ToolDefinition(name, "Read Git data", {"type": "object", "properties": {}})
            for name in ("get_current_branch", "get_status", "get_recent_commits", "get_diff")
        ]

    def call_evidence(self, name: str, repository_root: Path) -> list[GitEvidence]:
        if name == "get_current_branch":
            branch = self.current_branch(repository_root)
            return [GitEvidence("Git branch", f"Current branch: {branch.branch}.")]
        if name == "get_status":
            return self.status(repository_root)
        if name == "get_recent_commits":
            return self.recent_commits(repository_root)
        if name == "get_diff":
            return self.diff(repository_root)
        raise AssertionError("Unexpected tool name")

    def current_branch(self, repository_root: Path) -> BranchContext:
        self.calls.append("branch")
        return BranchContext("fixture/main", False, None)

    def status(self, repository_root: Path) -> list[GitEvidence]:
        self.calls.append("status")
        return [GitEvidence("Git status: src/example.py", " M src/example.py")]

    def recent_commits(self, repository_root: Path) -> list[GitEvidence]:
        self.calls.append("history")
        return [GitEvidence("commit " + "a" * 40, "a" * 40 + " Add invented feature")]

    def diff(self, repository_root: Path) -> list[GitEvidence]:
        self.calls.append("diff")
        return [GitEvidence("src/example.py (unstaged diff)", "+invented change")]


def _service(repository: Path, tmp_path: Path, git: FakeGit, chat: FakeChat) -> HelpService:
    config = load_config(tmp_path / "config.toml")
    embeddings = FakeEmbeddings()
    store = IndexStore(index_database_path(repository, tmp_path / "indexes"))
    sync = IndexSynchronizer(
        repository_root=repository,
        store=store,
        embedding_provider=embeddings,
        embedding_model=config.embedding_model,
        embedding_dimensions=config.embedding_dimensions,
        max_file_bytes=config.max_file_bytes,
    )
    sync.sync()
    return HelpService(config, repository, store, sync, embeddings, chat, git, True)


def test_git_questions_use_only_requested_tools_and_verified_citations(
    git_repository: Path, tmp_path: Path
) -> None:
    git = FakeGit()
    chat = FakeChat("Changed file [G1].", selected_tool="get_diff")
    service = _service(git_repository, tmp_path, git, chat)

    answer = service.answer("Что изменилось в рабочем дереве?")

    assert git.calls == ["diff"]
    assert "[src/example.py (unstaged diff)]" in answer
    assert "+invented change" in chat.tool_outputs[0]
    assert "Documentation excerpts" not in chat.prompts[0]
    assert "get_status" in chat.schemas[0]


def test_git_answer_rejects_unsupported_source(git_repository: Path, tmp_path: Path) -> None:
    chat = FakeChat("Invented assertion [G9].", selected_tool="get_status")
    service = _service(git_repository, tmp_path, FakeGit(), chat)

    assert "do not provide enough evidence" in service.answer("Show git status")


def test_branch_question_about_project_uses_model_tool_choice(
    git_repository: Path, tmp_path: Path
) -> None:
    chat = FakeChat("Branch [G1].", selected_tool="get_current_branch")
    service = _service(git_repository, tmp_path, FakeGit(), chat)

    assert service.answer("Какая ветка проекта сейчас?") == "Branch [Git branch]."
    assert chat.schemas[0][0] == "get_current_branch"


def test_warning_precedes_git_data_sent_to_chat(git_repository: Path, tmp_path: Path) -> None:
    config = load_config(tmp_path / "config.toml")
    events: list[str] = []

    class RecordingChat(FakeChat):
        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Sequence[ToolDefinition],
            call_tool: Callable[[str, dict[str, object]], str],
        ) -> str:
            events.append("chat")
            return super().generate_with_tools(instructions, prompt, tools, call_tool)

    lines = iter(["/help Show git status", "/exit"])
    git = FakeGit()
    run_session(
        repository_root=git_repository,
        config=config,
        input_fn=lambda prompt: next(lines),
        output_fn=events.append,
        embedding_provider=FakeEmbeddings(),
        chat_generator=RecordingChat("Status [G1].", selected_tool="get_status"),
        branch_provider=git,
        git_provider=git,
        index_directory=tmp_path / "indexes",
    )
    assert next(
        i for i, event in enumerate(events) if event.startswith("Privacy notice:")
    ) < events.index("chat")
    assert "uncommitted diff" in " ".join(events)
