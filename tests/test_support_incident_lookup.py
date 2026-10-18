import json
from collections.abc import Callable, Sequence
from pathlib import Path

from code_assistance.models import ToolDefinition
from support_demo.service import SupportService


class Embeddings:
    def embed(self, texts: Sequence[str], dimensions: int | None = None) -> list[list[float]]:
        del dimensions
        return [[float("оплат" in text.casefold()), 1.0] for text in texts]


class Data:
    def list_users(self) -> list[dict[str, str]]:
        raise AssertionError("The service should not list users")

    def get_user(self, user_id: str) -> dict[str, str]:
        raise AssertionError("The incident question does not need a profile")

    def list_visible_tickets(self, user_id: str) -> list[dict[str, str]]:
        assert user_id == "maria"
        return [
            {
                "id": "INC-101",
                "scope": "global",
                "title": "Сбой онлайн-оплаты",
                "description": "Часть платежей завершается ошибкой на сервере.",
                "status": "Уже чиним",
                "source": "tickets.json:L1",
            }
        ]


class Chat:
    def generate(self, instructions: str, prompt: str) -> str:
        raise AssertionError("Expected tool-capable chat")

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        assert "shared incident" in instructions
        assert "call list_visible_tickets" in instructions
        assert "shared incidents" in next(
            tool.description for tool in tools if tool.name == "list_visible_tickets"
        )
        tickets = json.loads(call_tool("list_visible_tickets", {}))["tickets"]
        assert tickets[0]["text"].startswith("INC-101. Сбой онлайн-оплаты")
        return "По общему инциденту INC-101: оплата может завершаться ошибкой. Уже чиним [T1]."


def test_global_payment_incident_is_looked_up(tmp_path: Path) -> None:
    (tmp_path / "product.md").write_text(
        "# Shop\n\nOnline payment is available.\n", encoding="utf-8"
    )
    (tmp_path / "faq.md").write_text("# FAQ\n\nCheck payment status.\n", encoding="utf-8")
    service = SupportService("maria", Data(), Embeddings(), Chat(), tmp_path)

    answer = service.answer("Расскажи о глобальном инциденте сбоя онлайн оплаты")

    assert "INC-101" in answer
    assert "Уже чиним" in answer
    assert "[T1]" not in answer
