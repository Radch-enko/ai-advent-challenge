import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from code_assistance.config import load_config
from code_assistance.errors import ProviderError
from code_assistance.models import ToolDefinition
from support_demo.__main__ import run_session
from support_demo.mcp_client import SupportDataError, SupportMCPClient
from support_demo.service import NO_EVIDENCE, SupportService


def _data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text(
        json.dumps(
            [
                {"id": "jane", "name": "Jane", "gender": "female"},
                {"id": "alex", "name": "Alex", "gender": "male"},
            ],
            ensure_ascii=False,
        ).replace("}, {", "},\n{")
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "tickets.json").write_text(
        json.dumps(
            [
                {
                    "id": "INC-1",
                    "scope": "global",
                    "title": "Сбой оплаты",
                    "description": "Ошибка на сервере при оплате.",
                    "status": "Уже чиним",
                },
                {
                    "id": "J-1",
                    "scope": "personal",
                    "user_id": "jane",
                    "title": "Письмо не пришло",
                    "description": "Jane не получила письмо.",
                    "status": "Ожидает проверки",
                },
                {
                    "id": "A-1",
                    "scope": "personal",
                    "user_id": "alex",
                    "title": "Сбой оплаты карты Alex",
                    "description": "Личная карта Alex отклонена.",
                    "status": "На рассмотрении",
                },
            ],
            ensure_ascii=False,
        ).replace("}, {", "},\n{")
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "product.md").write_text(
        "# Demo product\n\nDigital orders are delivered by email.\n", encoding="utf-8"
    )
    (data_dir / "faq.md").write_text(
        "# FAQ\n\n## Оплата\nПри ошибке оплаты уточните статус инцидента.\n"
        "\n## Возврат\nДля возврата обратитесь в поддержку.\n",
        encoding="utf-8",
    )
    return data_dir


class FakeEmbeddings:
    def embed(self, texts: Sequence[str], dimensions: int | None = None) -> list[list[float]]:
        del dimensions
        result = []
        for text in texts:
            lowered = text.casefold()
            result.append(
                [
                    float("оплат" in lowered or "карта" in lowered),
                    float("письм" in lowered or "email" in lowered),
                    float("возврат" in lowered),
                ]
            )
        return result


class FakeChat:
    def __init__(self, response: str = "Здравствуйте, Jane [U1]. Сбой уже чиним [T1].") -> None:
        self.response = response
        self.tool_results: dict[str, dict[str, object]] = {}
        self.prompt = ""
        self.instructions = ""

    def generate(self, instructions: str, prompt: str) -> str:
        raise AssertionError("Expected MCP tool flow")

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        self.instructions = instructions
        self.prompt = prompt
        assert {tool.name for tool in tools} == {"get_user", "list_visible_tickets"}
        for name in ("get_user", "list_visible_tickets"):
            self.tool_results[name] = json.loads(call_tool(name, {}))
        return self.response


def test_real_mcp_filters_other_users_tickets(tmp_path: Path) -> None:
    client = SupportMCPClient(_data_dir(tmp_path))
    assert [user["name"] for user in client.list_users()] == ["Jane", "Alex"]
    assert client.get_user("jane")["source"].startswith(str(tmp_path / "data" / "users.json"))
    jane_ids = {item["id"] for item in client.list_visible_tickets("jane")}
    alex_ids = {item["id"] for item in client.list_visible_tickets("alex")}
    assert jane_ids == {"INC-1", "J-1"}
    assert alex_ids == {"INC-1", "A-1"}


def test_payment_answer_uses_rag_without_exposing_sources(tmp_path: Path) -> None:
    data_dir = _data_dir(tmp_path)
    chat = FakeChat()
    service = SupportService("jane", SupportMCPClient(data_dir), FakeEmbeddings(), chat, data_dir)
    answer = service.answer("Почему не работает оплата?")

    assert "Jane" in answer
    assert "уже чиним" in answer
    assert "users.json" not in answer
    assert "tickets.json" not in answer
    assert "[U1]" not in answer
    assert "[T1]" not in answer
    assert "оплата" in chat.prompt
    assert "customer support" in chat.instructions
    assert "Never offer" in chat.instructions
    assert "INC-1" in str(chat.tool_results["list_visible_tickets"])
    assert "Alex" not in str(chat.tool_results["list_visible_tickets"])
    assert chat.tool_results["get_user"]["source_id"] == "[U1]"
    assert chat.tool_results["list_visible_tickets"]["tickets"][0]["source_id"] == "[T1]"
    assert str(data_dir) not in str(chat.tool_results)
    assert service.history == [("Почему не работает оплата?", answer)]


def test_unverified_answer_is_rejected(tmp_path: Path) -> None:
    data_dir = _data_dir(tmp_path)
    chat = FakeChat("Срок исправления — завтра [U1].")
    service = SupportService("jane", SupportMCPClient(data_dir), FakeEmbeddings(), chat, data_dir)
    assert service.answer("Почему не работает оплата?") == NO_EVIDENCE
    assert not service.history


def test_faq_answer_uses_document_when_no_ticket_matches(tmp_path: Path) -> None:
    data_dir = _data_dir(tmp_path)
    chat = FakeChat("Jane [U1], для возврата обратитесь в поддержку [S2].")
    service = SupportService("jane", SupportMCPClient(data_dir), FakeEmbeddings(), chat, data_dir)
    answer = service.answer("Как оформить возврат?")
    assert answer == "Jane, для возврата обратитесь в поддержку."
    assert chat.tool_results["list_visible_tickets"] == {"tickets": []}


def test_updated_ticket_status_is_read_again(tmp_path: Path) -> None:
    data_dir = _data_dir(tmp_path)

    class StatusChat(FakeChat):
        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Sequence[ToolDefinition],
            call_tool: Callable[[str, dict[str, object]], str],
        ) -> str:
            call_tool("get_user", {})
            tickets = json.loads(call_tool("list_visible_tickets", {}))["tickets"]
            return f"Jane [U1], {tickets[0]['text']} [T1]."

    service = SupportService(
        "jane", SupportMCPClient(data_dir), FakeEmbeddings(), StatusChat(), data_dir
    )
    assert "Уже чиним" in service.answer("Не работает оплата")
    path = data_dir / "tickets.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Уже чиним", "Исправлено"),
        encoding="utf-8",
    )
    second = service.answer("Не работает оплата")
    assert "Исправлено" in second
    assert "Уже чиним" not in second


def test_cli_selects_user_and_warns_before_embedding(tmp_path: Path) -> None:
    data_dir = _data_dir(tmp_path)
    output: list[str] = []

    class OrderedEmbeddings(FakeEmbeddings):
        def embed(self, texts: Sequence[str], dimensions: int | None = None) -> list[list[float]]:
            assert any(line.startswith("Privacy notice:") for line in output)
            return super().embed(texts, dimensions)

    inputs = iter(["3", "1", "Почему не работает оплата?", "/exit"])
    run_session(
        load_config(tmp_path / "missing.toml"),
        data_dir,
        input_fn=lambda _: next(inputs),
        output_fn=output.append,
        embeddings=OrderedEmbeddings(),
        chat=FakeChat(),
    )
    assert "Выберите номер из списка." in output
    assert any("Jane" in line and "уже чиним" in line for line in output)
    assert not any("tickets.json:L" in line for line in output)


def test_provider_and_mcp_failures_are_explicit(tmp_path: Path) -> None:
    data_dir = _data_dir(tmp_path)

    class BrokenChat(FakeChat):
        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Sequence[ToolDefinition],
            call_tool: Callable[[str, dict[str, object]], str],
        ) -> str:
            raise ProviderError("Synthetic provider failure.")

    service = SupportService(
        "jane", SupportMCPClient(data_dir), FakeEmbeddings(), BrokenChat(), data_dir
    )
    with pytest.raises(ProviderError, match="Synthetic provider failure"):
        service.answer("Оплата не работает")

    class InvalidToolChat(FakeChat):
        def generate_with_tools(
            self,
            instructions: str,
            prompt: str,
            tools: Sequence[ToolDefinition],
            call_tool: Callable[[str, dict[str, object]], str],
        ) -> str:
            return call_tool("get_user", {"user_id": "alex"})

    service.chat = InvalidToolChat()
    with pytest.raises(SupportDataError, match="invalid support tool"):
        service.answer("Оплата не работает")

    (data_dir / "tickets.json").unlink()
    with pytest.raises(SupportDataError, match="Support MCP"):
        SupportMCPClient(data_dir).list_visible_tickets("jane")
