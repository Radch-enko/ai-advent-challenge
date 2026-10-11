from __future__ import annotations

import argparse
import os
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_API_URL = "http://127.0.0.1:8000"
HTTP_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1024 * 1024


class DailyJournalChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(pattern="^(add|replace|remove|complete_task)$")
    section: str = Field(pattern="^(main|notes|ideas|next_steps|gratitude)$")
    text: str = Field(min_length=1, max_length=2000)
    previous_text: str | None = Field(default=None, min_length=1, max_length=2000)


class DailyJournalNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    content: str
    revision: str | None = None
    exists: bool
    changed: bool = False


class CopiaApiClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def read(self, note_date: date) -> DailyJournalNote:
        payload = await self._request("GET", f"/daily-journal/{note_date.isoformat()}")
        return self._validate_response(payload)

    async def apply(
        self,
        note_date: date,
        *,
        expected_revision: str | None,
        changes: list[DailyJournalChange],
    ) -> DailyJournalNote:
        payload = await self._request(
            "PATCH",
            f"/daily-journal/{note_date.isoformat()}",
            json={
                "expected_revision": expected_revision,
                "changes": [change.model_dump(mode="json") for change in changes],
            },
        )
        return self._validate_response(payload)

    async def _request(self, method: str, path: str, **kwargs: Any) -> object:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url(),
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=False,
                transport=self._transport,
                trust_env=False,
            ) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            raise ToolError("Copia API request timed out") from error
        except httpx.RequestError as error:
            raise ToolError("Copia API is unavailable") from error

        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ToolError("Copia API response is too large")
        if response.is_error or response.is_redirect:
            if response.status_code == 409:
                raise ToolError("Daily journal note changed; read it again before editing")
            if response.status_code == 422:
                raise ToolError("Daily journal request is invalid")
            raise ToolError("Copia API rejected the daily journal request")
        try:
            return response.json()
        except ValueError as error:
            raise ToolError("Copia API returned an invalid response") from error

    @staticmethod
    def _base_url() -> str:
        raw_url = os.getenv("COPIA_API_URL", DEFAULT_API_URL).strip().rstrip("/")
        parsed = urlsplit(raw_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ToolError("COPIA_API_URL is invalid")
        return raw_url

    @staticmethod
    def _validate_response(payload: object) -> DailyJournalNote:
        try:
            return DailyJournalNote.model_validate(payload)
        except ValidationError as error:
            raise ToolError("Copia API returned an invalid daily journal note") from error


server = MCPServer("copia-journal")
api_client = CopiaApiClient()
JOURNAL_TIMEZONE = ZoneInfo("Asia/Omsk")


def _parse_note_date(note_date: str | None) -> date:
    if note_date is None:
        return datetime.now(JOURNAL_TIMEZONE).date()
    try:
        parsed_date = date.fromisoformat(note_date)
    except ValueError as error:
        raise ToolError("note_date must use YYYY-MM-DD format") from error
    if parsed_date.isoformat() != note_date:
        raise ToolError("note_date must use YYYY-MM-DD format")
    return parsed_date


@server.tool(
    name="get_daily_journal",
    description="Read one daily journal note by its ISO date before proposing edits.",
    structured_output=True,
)
async def get_daily_journal(note_date: str | None = None) -> DailyJournalNote:
    return await api_client.read(_parse_note_date(note_date))


@server.tool(
    name="apply_daily_journal_changes",
    description=(
        "Apply confirmed add, replace, remove, or task-completion operations to one daily note. "
        "Read the note first and pass its revision. Use only facts stated by the user."
    ),
    structured_output=True,
)
async def apply_daily_journal_changes(
    expected_revision: str | None,
    changes: list[DailyJournalChange],
    note_date: str | None = None,
) -> DailyJournalNote:
    if not changes:
        raise ToolError("At least one daily journal change is required")
    return await api_client.apply(
        _parse_note_date(note_date),
        expected_revision=expected_revision,
        changes=changes,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Copia Journal MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.transport == "stdio":
            server.run("stdio")
            return
        server.run(
            "streamable-http",
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8002")),
            streamable_http_path="/mcp",
        )
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
