from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

import server as finances_server


def run(coroutine):
    return asyncio.run(coroutine)


def _expense_payload() -> dict[str, object]:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "occurred_at": "2026-09-23T14:30:00+06:00",
        "name": "Gym",
        "category": "Sport",
        "amount_rub": "2500.00",
        "merchant": None,
        "payment_method": "Card",
        "note": None,
        "tags": ["health"],
        "created_at": "2026-09-23T08:30:00+00:00",
    }


def test_mcp_protocol_lists_exact_tools_and_returns_structured_output(monkeypatch) -> None:
    class FakeApiClient:
        async def search_expenses(self, request):
            return finances_server.ExpensePage(
                items=[finances_server.Expense.model_validate(_expense_payload())]
            )

        async def add_expense(self, request):
            return finances_server.Expense.model_validate(_expense_payload())

    monkeypatch.setattr(finances_server, "api_client", FakeApiClient())

    async def exercise():
        async with Client(finances_server.server, mode="legacy", cache=None) as client:
            listing = await client.list_tools()
            result = await client.call_tool("search_expenses", {"category": "sport"})
            return listing, result

    listing, result = run(exercise())

    assert {tool.name for tool in listing.tools} == {"search_expenses", "add_expense"}
    search_schema = next(
        tool.input_schema for tool in listing.tools if tool.name == "search_expenses"
    )
    assert {"occurred_from", "category", "tags", "page_size", "cursor"} <= set(
        search_schema["properties"]
    )
    assert result.is_error is False
    assert result.structured_content["items"][0]["name"] == "Gym"


def test_http_client_serializes_search_filters(monkeypatch) -> None:
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(200, json={"items": [], "next_cursor": None})

    monkeypatch.setenv("COPIA_API_URL", "http://127.0.0.1:8000")
    client = finances_server.CopiaApiClient(httpx.MockTransport(handler))
    request = finances_server.ExpenseSearchRequest(
        occurred_from=datetime(2026, 9, 1, tzinfo=UTC),
        category="Food",
        tags=["weekly", "family"],
        min_amount_rub=Decimal("10.50"),
        page_size=10,
        cursor="cursor-value",
    )

    result = run(client.search_expenses(request))

    assert result.items == []
    assert seen_request is not None
    assert seen_request.url.path == "/expenses"
    assert seen_request.url.params.get("category") == "Food"
    assert seen_request.url.params.get_list("tags") == ["weekly", "family"]
    assert seen_request.url.params.get("min_amount_rub") == "10.50"
    assert seen_request.url.params.get("cursor") == "cursor-value"


def test_http_client_serializes_add_payload(monkeypatch) -> None:
    seen_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        seen_payload = __import__("json").loads(request.content)
        return httpx.Response(201, json=_expense_payload())

    monkeypatch.setenv("COPIA_API_URL", "http://127.0.0.1:8000")
    client = finances_server.CopiaApiClient(httpx.MockTransport(handler))
    request = finances_server.ExpenseCreate(
        occurred_at=datetime.fromisoformat("2026-09-23T14:30:00+06:00"),
        name="Gym",
        category="Sport",
        amount_rub=Decimal("2500.00"),
        payment_method="Card",
        tags=["health"],
    )

    result = run(client.add_expense(request))

    assert result.id == UUID("00000000-0000-0000-0000-000000000001")
    assert seen_payload["amount_rub"] == "2500.00"
    assert seen_payload["occurred_at"] == "2026-09-23T14:30:00+06:00"


@pytest.mark.parametrize(
    ("handler", "expected_message"),
    [
        (
            lambda request: httpx.Response(
                422, json={"detail": {"code": "invalid", "message": "Invalid range"}}
            ),
            "Invalid range",
        ),
        (lambda request: httpx.Response(200, text="not-json"), "invalid response"),
        (lambda request: httpx.Response(200, json={"unexpected": True}), "invalid response"),
    ],
)
def test_http_client_converts_backend_failures(monkeypatch, handler, expected_message) -> None:
    monkeypatch.setenv("COPIA_API_URL", "http://127.0.0.1:8000")
    client = finances_server.CopiaApiClient(httpx.MockTransport(handler))

    with pytest.raises(ToolError, match=expected_message):
        run(client.search_expenses(finances_server.ExpenseSearchRequest()))


@pytest.mark.parametrize(
    ("exception", "expected_message"),
    [
        (httpx.ConnectError("secret endpoint"), "Copia API is unavailable"),
        (httpx.ReadTimeout("secret endpoint"), "Copia API request timed out"),
    ],
)
def test_http_client_hides_network_failure_details(
    monkeypatch, exception, expected_message
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    monkeypatch.setenv("COPIA_API_URL", "http://127.0.0.1:8000")
    client = finances_server.CopiaApiClient(httpx.MockTransport(handler))

    with pytest.raises(ToolError) as error:
        run(client.search_expenses(finances_server.ExpenseSearchRequest()))

    assert str(error.value) == expected_message
    assert "secret" not in str(error.value)
