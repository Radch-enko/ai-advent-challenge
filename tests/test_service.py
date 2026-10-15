from collections.abc import Callable, Sequence
from pathlib import Path

from code_assistance.config import load_config
from code_assistance.errors import BranchUnavailableError, GitUnavailableError
from code_assistance.index_store import IndexStore
from code_assistance.indexing import IndexSynchronizer, index_database_path
from code_assistance.models import BranchContext, GitEvidence, ToolDefinition
from code_assistance.service import HelpService
from tests.conftest import FakeEmbeddings


class FakeChat:
    def __init__(
        self,
        response: str = "[S1] The project layout is described here.",
        selected_tool: str | None = None,
    ) -> None:
        self.response = response
        self.selected_tool = selected_tool
        self.calls: list[tuple[str, str]] = []
        self.schemas: list[list[str]] = []

    def generate(self, instructions: str, prompt: str) -> str:
        self.calls.append((instructions, prompt))
        return self.response

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        self.calls.append((instructions, prompt))
        self.schemas.append([tool.name for tool in tools])
        if self.selected_tool:
            call_tool(self.selected_tool, {})
        return self.response


class FakeBranch:
    def __init__(self, contexts: list[BranchContext] | None = None) -> None:
        self.contexts = contexts or [BranchContext("main", False, "0123456789abcdef")]
        self.calls = 0

    def current_branch(self, repository_root: Path) -> BranchContext:
        del repository_root
        context = self.contexts[min(self.calls, len(self.contexts) - 1)]
        self.calls += 1
        return context

    def available_tools(self, repository_root: Path) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "get_current_branch", "Read branch", {"type": "object", "properties": {}}
            )
        ]

    def call_evidence(self, name: str, repository_root: Path) -> list[GitEvidence]:
        assert name == "get_current_branch"
        branch = self.current_branch(repository_root)
        text = (
            f"HEAD is detached at {branch.commit_sha}."
            if branch.detached
            else f"Current branch: {branch.branch}."
        )
        return [GitEvidence("Git branch", text)]


class UnavailableBranch:
    def current_branch(self, repository_root: Path) -> BranchContext:
        del repository_root
        raise BranchUnavailableError("MCP server is not configured.")

    def available_tools(self, repository_root: Path) -> list[ToolDefinition]:
        raise GitUnavailableError("MCP server is not configured.")

    def call_evidence(self, name: str, repository_root: Path) -> list[GitEvidence]:
        raise GitUnavailableError("MCP server is not configured.")


def _service(
    repository: Path,
    tmp_path: Path,
    embeddings: FakeEmbeddings,
    chat: FakeChat,
    branch: FakeBranch | UnavailableBranch,
) -> HelpService:
    config = load_config(tmp_path / "config.toml")
    store = IndexStore(index_database_path(repository, tmp_path / "indexes"))
    synchronizer = IndexSynchronizer(
        repository_root=repository,
        store=store,
        embedding_provider=embeddings,
        embedding_model=config.embedding_model,
        embedding_dimensions=config.embedding_dimensions,
        max_file_bytes=config.max_file_bytes,
    )
    synchronizer.sync()
    return HelpService(
        config=config,
        repository_root=repository,
        store=store,
        synchronizer=synchronizer,
        embedding_provider=embeddings,
        chat_generator=chat,
        git_provider=branch,
        index_ready=True,
    )


def test_document_answer_uses_retrieved_text_and_validated_citation(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text(
        "The project layout is described in this document.", encoding="utf-8"
    )
    chat = FakeChat()
    service = _service(git_repository, tmp_path, fake_embeddings, chat, FakeBranch())

    answer = service.answer("Where is the project layout described?")

    assert "docs/architecture.md:L1" in answer
    assert len(chat.calls) == 1
    assert "[S1]" in chat.calls[0][1]
    assert "untrusted data" in chat.calls[0][0]


def test_question_about_branch_uses_model_selected_mcp_tool(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    changing_branch = FakeBranch(
        [
            BranchContext("feature/first", False, "0123456789abcdef"),
            BranchContext("feature/second", False, "fedcba9876543210"),
        ]
    )
    chat = FakeChat("Current branch [G1].", selected_tool="get_current_branch")
    service = _service(git_repository, tmp_path, fake_embeddings, chat, changing_branch)
    fake_embeddings.calls.clear()

    first = service.answer("Какая сейчас ветка?")
    second = service.answer("What is the current branch?")

    assert first == "Current branch [Git branch]."
    assert second == "Current branch [Git branch]."
    assert changing_branch.calls == 2
    assert not fake_embeddings.calls
    assert len(chat.calls) == 2
    assert chat.schemas == [["get_current_branch"], ["get_current_branch"]]


def test_detached_head_and_mcp_failure_are_explicit(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    detached = FakeBranch([BranchContext(None, True, "0123456789abcdef")])
    detached_service = _service(
        git_repository,
        tmp_path / "detached",
        fake_embeddings,
        FakeChat("Detached HEAD [G1].", selected_tool="get_current_branch"),
        detached,
    )
    unavailable_service = _service(
        git_repository,
        tmp_path / "unavailable",
        fake_embeddings,
        FakeChat(),
        UnavailableBranch(),
    )

    assert "[Git branch]" in detached_service.answer("What branch is checked out?")
    assert "Git MCP tools are unavailable" in unavailable_service.answer(
        "Which branch is checked out?"
    )


def test_unknown_citations_or_answers_without_citations_are_rejected(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("The project structure is documented.", encoding="utf-8")

    unknown_id = _service(
        git_repository,
        tmp_path / "unknown",
        fake_embeddings,
        FakeChat("[S9] A made-up answer."),
        FakeBranch(),
    )
    missing_id = _service(
        git_repository,
        tmp_path / "missing",
        fake_embeddings,
        FakeChat("A made-up answer without a source."),
        FakeBranch(),
    )

    assert "does not provide enough evidence" in unknown_id.answer("Where is the structure?")
    assert "does not provide enough evidence" in missing_id.answer("Where is the structure?")


def test_irrelevant_question_abstains_without_calling_chat(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("The project structure is documented.", encoding="utf-8")
    chat = FakeChat()
    service = _service(git_repository, tmp_path, fake_embeddings, chat, FakeBranch())

    answer = service.answer("What does the release policy say?")

    assert "does not provide enough evidence" in answer
    assert len(chat.calls) == 1


def test_empty_documentation_can_still_offer_git_tools(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    chat = FakeChat()
    service = _service(git_repository, tmp_path, fake_embeddings, chat, FakeBranch())
    fake_embeddings.calls.clear()

    answer = service.answer("Where is the project structure documented?")

    assert "does not provide enough evidence" in answer
    assert not fake_embeddings.calls
    assert chat.schemas == [["get_current_branch"]]


def test_document_answer_marks_unavailable_branch(
    git_repository: Path,
    tmp_path: Path,
    fake_embeddings: FakeEmbeddings,
) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("The project layout is documented.", encoding="utf-8")
    service = _service(
        git_repository,
        tmp_path,
        fake_embeddings,
        FakeChat(),
        UnavailableBranch(),
    )

    answer = service.answer("Where is the project layout described?")

    assert "docs/architecture.md" in answer
    assert "Git MCP tools are unavailable" in answer
