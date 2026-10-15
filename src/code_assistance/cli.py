import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from code_assistance.config import (
    AppConfig,
    default_index_directory,
    load_config,
)
from code_assistance.errors import CodeAssistanceError
from code_assistance.index_store import IndexStore
from code_assistance.indexing import IndexSynchronizer, index_database_path
from code_assistance.mcp_client import MCPBranchProvider
from code_assistance.ports import BranchProvider, ChatGenerator, EmbeddingProvider, GitProvider
from code_assistance.providers import OpenAIProvider
from code_assistance.repository import find_repository_root
from code_assistance.service import HelpService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code-assistance",
        description="Answer read-only questions about a Git repository with /help.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        help="Git repository or directory inside it (defaults to the current directory).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repository_root = find_repository_root(args.repo or Path.cwd())
        config = load_config()
        run_session(repository_root, config)
    except CodeAssistanceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nGoodbye.")
    return 0


def run_session(
    repository_root: Path,
    config: AppConfig,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    embedding_provider: EmbeddingProvider | None = None,
    chat_generator: ChatGenerator | None = None,
    branch_provider: BranchProvider | None = None,
    git_provider: GitProvider | None = None,
    index_directory: Path | None = None,
) -> None:
    output_fn(f"OpenAI endpoint: {config.base_url}")
    output_fn(
        "Privacy notice: questions, relevant documentation excerpts, and selected Git data "
        "(including uncommitted diff) may be sent to OpenAI."
    )

    default_provider = OpenAIProvider(config)
    provider = embedding_provider or default_provider
    chat = chat_generator or default_provider
    git = git_provider or (
        branch_provider
        if isinstance(branch_provider, MCPBranchProvider)
        else MCPBranchProvider(config)
    )
    index_path = index_database_path(
        repository_root,
        index_directory or default_index_directory(),
    )
    store = IndexStore(index_path)
    synchronizer = IndexSynchronizer(
        repository_root=repository_root,
        store=store,
        embedding_provider=provider,
        embedding_model=config.embedding_model,
        embedding_dimensions=config.embedding_dimensions,
        max_file_bytes=config.max_file_bytes,
    )

    index_ready = True
    index_error: str | None = None
    try:
        result = synchronizer.sync()
        output_fn(
            "Documentation index ready: "
            f"{result.indexed_document_count} file(s), "
            f"{result.changed_document_count} updated, "
            f"{result.removed_document_count} removed."
        )
        for warning in result.warnings:
            output_fn(f"Warning: {warning}")
    except CodeAssistanceError as exc:
        index_ready = False
        index_error = str(exc)
        output_fn(f"Warning: documentation index refresh failed: {exc}")

    service = HelpService(
        config=config,
        repository_root=repository_root,
        store=store,
        synchronizer=synchronizer,
        embedding_provider=provider,
        chat_generator=chat,
        git_provider=git,
        index_ready=index_ready,
        index_error=index_error,
    )
    output_fn("Enter /help <question> or /exit.")

    while True:
        try:
            line = input_fn("> ").strip()
        except EOFError:
            output_fn("Goodbye.")
            return
        except KeyboardInterrupt:
            output_fn("\nGoodbye.")
            return

        if not line:
            continue
        if line == "/exit":
            output_fn("Goodbye.")
            return
        if line == "/help":
            output_fn("Usage: /help <question>")
            continue
        if line.startswith("/help "):
            question = line[len("/help ") :].strip()
            try:
                output_fn(service.answer(question))
            except CodeAssistanceError as exc:
                output_fn(f"Error: {exc}")
            continue
        output_fn("Unknown command. Use /help <question> or /exit.")
