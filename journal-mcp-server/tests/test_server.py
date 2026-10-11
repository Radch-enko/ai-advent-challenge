from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx
import pytest
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

import server as journal_server


def run(coroutine):
    return asyncio.run(coroutine)


def _note_payload() -> dict[str, object]:
    return {
        "date": "2026-10-11",
        "content": "# 2026-10-11\n",
        "revision": "a" * 64,
        "exists": True,
        "changed": True,
    }


def test_mcp_protocol_lists_journal_tools_and_strict_arguments(monkeypatch) -> None:
    class FakeApiClient:
        async def read(self, note_date):
            assert note_date == date(2026, 10, 11)
            return journal_server.DailyJournalNote.model_validate(_note_payload())

        async def apply(self, note_date, *, expected_revision, changes):
            assert note_date == date(2026, 10, 11)
            assert expected_revision == "a" * 64
            assert changes[0].operation == "add"
            return journal_server.DailyJournalNote.model_validate(_note_payload())

    monkeypatch.setattr(journal_server, "api_client", FakeApiClient())

    async def exercise():
        async with Client(journal_server.server, mode="legacy", cache=None) as client:
            listing = await client.list_tools()
            read_result = await client.call_tool("get_daily_journal", {"note_date": "2026-10-11"})
            write_result = await client.call_tool(
                "apply_daily_journal_changes",
                {
                    "note_date": "2026-10-11",
                    "expected_revision": "a" * 64,
                    "changes": [
                        {
                            "operation": "add",
                            "section": "main",
                            "text": "Подготовил тестовый пример",
                        }
                    ],
                },
            )
            return listing, read_result, write_result

    listing, read_result, write_result = run(exercise())

    assert {tool.name for tool in listing.tools} == {
        "get_daily_journal",
        "apply_daily_journal_changes",
    }
    write_schema = next(
        tool.input_schema for tool in listing.tools if tool.name == "apply_daily_journal_changes"
    )
    assert {"note_date", "expected_revision", "changes"} <= set(write_schema["properties"])
    assert read_result.is_error is False
    assert write_result.is_error is False


def test_api_client_uses_backend_read_and_patch_routes(monkeypatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_note_payload())

    monkeypatch.setenv("COPIA_API_URL", "http://127.0.0.1:8000")
    client = journal_server.CopiaApiClient(httpx.MockTransport(handler))
    changes = [
        journal_server.DailyJournalChange(
            operation="add",
            section="main",
            text="Подготовил тестовый пример",
        )
    ]

    result = run(client.apply(date(2026, 10, 11), expected_revision=None, changes=changes))

    assert result.date == date(2026, 10, 11)
    assert seen[0].method == "PATCH"
    assert seen[0].url.path == "/daily-journal/2026-10-11"
    assert json.loads(seen[0].content) == {
        "expected_revision": None,
        "changes": [
            {
                "operation": "add",
                "section": "main",
                "text": "Подготовил тестовый пример",
                "previous_text": None,
            }
        ],
    }


def test_api_client_reports_revision_conflict_without_leaking_body(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "private note content"})

    monkeypatch.setenv("COPIA_API_URL", "http://127.0.0.1:8000")
    client = journal_server.CopiaApiClient(httpx.MockTransport(handler))
    change = journal_server.DailyJournalChange(
        operation="add", section="notes", text="Synthetic note text"
    )

    with pytest.raises(ToolError, match="read it again"):
        run(client.apply(date(2026, 10, 11), expected_revision="b" * 64, changes=[change]))
