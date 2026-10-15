from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from code_assistance.models import BranchContext, GitEvidence, ToolDefinition


class ChatGenerator(Protocol):
    def generate(self, instructions: str, prompt: str) -> str:
        """Generate an answer without exposing provider-specific response types."""

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        """Let the model choose tools and return their results in the same response flow."""


class EmbeddingProvider(Protocol):
    def embed(
        self,
        texts: Sequence[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Return one finite, non-empty vector for each input text."""


class BranchProvider(Protocol):
    def current_branch(self, repository_root: Path) -> BranchContext:
        """Read current Git context through the configured MCP server."""


class GitProvider(Protocol):
    def available_tools(self, repository_root: Path) -> list[ToolDefinition]: ...

    def call_evidence(self, name: str, repository_root: Path) -> list[GitEvidence]: ...

    def status(self, repository_root: Path) -> list[GitEvidence]: ...

    def recent_commits(self, repository_root: Path) -> list[GitEvidence]: ...

    def diff(self, repository_root: Path) -> list[GitEvidence]: ...
