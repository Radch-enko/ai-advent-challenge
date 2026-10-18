import json
from collections.abc import Callable, Sequence
from pathlib import Path

from code_assistance.models import ToolDefinition
from support_demo.service import SupportService


class Embeddings:
    def embed(self, texts: Sequence[str], dimensions: int | None = None) -> list[list[float]]:
        del dimensions
        return [[1.0] for _ in texts]


class Data:
    def __init__(self, root: Path) -> None:
        self.root = root

    def list_users(self) -> list[dict[str, str]]:
        raise AssertionError("The service should not list users")

    def get_user(self, user_id: str) -> dict[str, str]:
        assert user_id == "maria"
        return {
            "id": "maria",
            "name": "Maria",
            "source": f"{self.root}/users.json:L2",
        }

    def list_visible_tickets(self, user_id: str) -> list[dict[str, str]]:
        assert user_id == "maria"
        return [
            {
                "id": "T-1",
                "scope": "personal",
                "user_id": "maria",
                "title": "Доставка заказа",
                "description": "Курьер ожидает подтверждения времени.",
                "status": "Проверяем",
                "source": f"{self.root}/tickets.json:L2",
            }
        ]


class Chat:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.prompt = ""
        self.tool_results: list[str] = []

    def generate(self, instructions: str, prompt: str) -> str:
        raise AssertionError("Expected tool-capable chat")

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        self.prompt = prompt
        self.tool_results = [
            call_tool("get_user", {}),
            call_tool("list_visible_tickets", {}),
        ]
        return "Добрый день, Maria [U1]. Доставка доступна [S1][T1]."


def test_internal_sources_are_hidden_from_model_and_customer(tmp_path: Path) -> None:
    (tmp_path / "product.md").write_text(
        "# Fictional shop\nCourier delivery is available.\n", encoding="utf-8"
    )
    (tmp_path / "faq.md").write_text("# FAQ\n", encoding="utf-8")
    chat = Chat(tmp_path)
    service = SupportService("maria", Data(tmp_path), Embeddings(), chat, tmp_path)

    answer = service.answer("Есть доставка?")

    assert answer == "Добрый день, Maria. Доставка доступна."
    assert str(tmp_path) not in chat.prompt
    assert all(str(tmp_path) not in result for result in chat.tool_results)
    assert json.loads(chat.tool_results[0])["source_id"] == "[U1]"
    assert json.loads(chat.tool_results[1])["tickets"][0]["source_id"] == "[T1]"
    assert str(tmp_path) not in answer
    assert service.history == [("Есть доставка?", answer)]
