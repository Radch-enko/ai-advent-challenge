from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from code_assistance.models import ToolDefinition
from support_demo.service import NO_EVIDENCE, SupportService


class CountingEmbeddings:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str], dimensions: int | None = None) -> list[list[float]]:
        del dimensions
        self.calls += 1
        return [[1.0] for _ in texts]


class GreetingChat:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, instructions: str, prompt: str) -> str:
        raise AssertionError("Greeting should not call the provider")

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        self.calls += 1
        return "Здравствуйте!"


class NoMCP:
    def get_user(self, user_id: str) -> dict[str, str]:
        raise AssertionError("Greeting should not read a user")

    def list_visible_tickets(self, user_id: str) -> list[dict[str, str]]:
        raise AssertionError("Greeting should not read tickets")

    def list_users(self) -> list[dict[str, str]]:
        raise AssertionError("Greeting should not list users")


@pytest.fixture
def service(tmp_path: Path) -> tuple[SupportService, CountingEmbeddings, GreetingChat]:
    (tmp_path / "product.md").write_text("# Fictional store\n", encoding="utf-8")
    (tmp_path / "faq.md").write_text("# FAQ\n", encoding="utf-8")
    embeddings = CountingEmbeddings()
    chat = GreetingChat()
    return SupportService("demo-user", NoMCP(), embeddings, chat, tmp_path), embeddings, chat


@pytest.mark.parametrize("question", ["Привет", "привет!", "Здравствуйте", "Добрый день!"])
def test_plain_greeting_gets_helpful_reply_without_rag(
    service: tuple[SupportService, CountingEmbeddings, GreetingChat], question: str
) -> None:
    assistant, embeddings, chat = service
    initial_calls = embeddings.calls

    answer = assistant.answer(question)

    assert answer == "Здравствуйте! Чем могу помочь с товарами, заказом, оплатой или доставкой?"
    assert assistant.history == [(question, answer)]
    assert embeddings.calls == initial_calls
    assert chat.calls == 0


def test_greeting_with_product_question_still_requires_evidence(
    service: tuple[SupportService, CountingEmbeddings, GreetingChat],
) -> None:
    assistant, embeddings, chat = service
    initial_calls = embeddings.calls

    assert assistant.answer("Привет, где мой заказ?") == NO_EVIDENCE
    assert embeddings.calls > initial_calls
    assert chat.calls == 1
