from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from code_assistance.models import ToolDefinition
from support_demo.service import NO_EVIDENCE, SupportService


class Embeddings:
    def embed(self, texts: Sequence[str], dimensions: int | None = None) -> list[list[float]]:
        del dimensions
        return [[1.0] for _ in texts]


class Data:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_users(self) -> list[dict[str, str]]:
        raise AssertionError("The service should not list users")

    def get_user(self, user_id: str) -> dict[str, str]:
        self.calls.append("get_user")
        assert user_id == "maria"
        return {"id": "maria", "name": "Maria", "source": "users.json:L2"}

    def list_visible_tickets(self, user_id: str) -> list[dict[str, str]]:
        self.calls.append("list_visible_tickets")
        assert user_id == "maria"
        return [
            {
                "id": "T-1",
                "scope": "personal",
                "user_id": "maria",
                "title": "Доставка",
                "description": "Заказ ожидает курьера.",
                "status": "Проверяем",
                "source": "tickets.json:L2",
            }
        ]


class SelectiveChat:
    def __init__(self, tool_names: tuple[str, ...], response: str) -> None:
        self.tool_names = tool_names
        self.response = response
        self.instructions = ""

    def generate(self, instructions: str, prompt: str) -> str:
        raise AssertionError("Expected the tool-capable chat method")

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        self.instructions = instructions
        assert {tool.name for tool in tools} == {"get_user", "list_visible_tickets"}
        for name in self.tool_names:
            call_tool(name, {})
        return self.response


@pytest.fixture
def documents(tmp_path: Path) -> Path:
    (tmp_path / "product.md").write_text(
        "# Demo shop\n\nCourier delivery is available.\n", encoding="utf-8"
    )
    (tmp_path / "faq.md").write_text("# FAQ\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("question", "tool_names", "response", "expected_answer"),
    [
        (
            "Какая доставка?",
            (),
            "Доступна курьерская доставка [S1].",
            "Доступна курьерская доставка.",
        ),
        ("Как меня зовут?", ("get_user",), "Добрый день, Maria [U1].", "Добрый день, Maria."),
        (
            "Какой статус обращения?",
            ("list_visible_tickets",),
            "Заказ проверяется [T1].",
            "Заказ проверяется.",
        ),
        (
            "Какая доставка?",
            ("get_user", "list_visible_tickets"),
            "Доступна курьерская доставка [S1].",
            "Доступна курьерская доставка.",
        ),
    ],
)
def test_model_may_choose_zero_one_or_two_tools(
    documents: Path,
    question: str,
    tool_names: tuple[str, ...],
    response: str,
    expected_answer: str,
) -> None:
    data = Data()
    chat = SelectiveChat(tool_names, response)
    service = SupportService("maria", data, Embeddings(), chat, documents)

    answer = service.answer(question)

    assert answer == expected_answer
    assert data.calls == list(tool_names)
    assert "Before answering every question, call list_visible_tickets" in chat.instructions


def test_missing_or_unavailable_citation_is_still_rejected(documents: Path) -> None:
    data = Data()
    for response in ("Товар уже доставлен.", "Заказ проверяется [T1]."):
        service = SupportService(
            "maria", data, Embeddings(), SelectiveChat((), response), documents
        )
        assert service.answer("Где заказ?") == NO_EVIDENCE
    assert data.calls == []
