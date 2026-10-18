"""Interactive CLI for the support demo."""

import sys
from collections.abc import Callable
from pathlib import Path

from code_assistance.config import AppConfig, load_config
from code_assistance.errors import CodeAssistanceError
from code_assistance.ports import ChatGenerator, EmbeddingProvider
from code_assistance.providers import OpenAIProvider
from support_demo.mcp_client import SupportData, SupportDataError, SupportMCPClient
from support_demo.service import SupportService


def run_session(
    config: AppConfig,
    data_dir: Path | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    embeddings: EmbeddingProvider | None = None,
    chat: ChatGenerator | None = None,
    data: SupportData | None = None,
) -> None:
    selected_dir = data_dir or Path(__file__).parent / "data"
    client = data or SupportMCPClient(selected_dir)
    users = client.list_users()
    if not users:
        raise SupportDataError("No demo users are available.")
    output_fn("Выберите пользователя:")
    for number, user in enumerate(users, 1):
        output_fn(f"{number}. {user['name']}")
    while True:
        selection = input_fn("Номер пользователя или /exit: ").strip()
        if selection == "/exit":
            return
        if selection.isdecimal() and 1 <= int(selection) <= len(users):
            user_id = users[int(selection) - 1]["id"]
            break
        output_fn("Выберите номер из списка.")

    output_fn(f"OpenAI endpoint: {config.base_url}")
    output_fn(
        "Privacy notice: questions, selected user profile, relevant FAQ/product excerpts "
        "and visible tickets may be sent to OpenAI."
    )
    sys.stdout.flush()
    provider = OpenAIProvider(config)
    service = SupportService(
        user_id,
        client,
        embeddings or provider,
        chat or provider,
        selected_dir,
    )
    output_fn("Задайте вопрос или введите /exit.")
    while True:
        try:
            question = input_fn("> ").strip()
        except EOFError:
            output_fn("До свидания.")
            return
        if question == "/exit":
            output_fn("До свидания.")
            return
        if not question:
            continue
        try:
            output_fn(service.answer(question))
        except (CodeAssistanceError, SupportDataError, ValueError) as exc:
            output_fn(f"Error: {exc}")


def main() -> int:
    try:
        run_session(load_config())
    except (CodeAssistanceError, SupportDataError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nДо свидания.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
