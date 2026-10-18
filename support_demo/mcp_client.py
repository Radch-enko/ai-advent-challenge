"""The support demo's narrow MCP transport boundary."""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Protocol

from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError


class SupportDataError(Exception):
    """An MCP read failed or returned an invalid shape."""


class SupportData(Protocol):
    def list_users(self) -> list[dict[str, str]]: ...

    def get_user(self, user_id: str) -> dict[str, str]: ...

    def list_visible_tickets(self, user_id: str) -> list[dict[str, str]]: ...


class SupportMCPClient:
    def __init__(self, data_dir: Path, timeout: float = 10.0) -> None:
        self.data_dir = data_dir.resolve(strict=True)
        self.timeout = timeout

    def _call(self, name: str, arguments: dict[str, str]) -> dict[str, Any]:
        if name not in {"list_users", "get_user", "list_visible_tickets"}:
            raise SupportDataError("Unsupported support MCP tool.")
        try:
            return asyncio.run(self._call_async(name, arguments))
        except (TimeoutError, OSError, MCPError, RuntimeError, ValueError) as exc:
            raise SupportDataError(
                "Support MCP server is unavailable or returned an error."
            ) from exc

    async def _call_async(self, name: str, arguments: dict[str, str]) -> dict[str, Any]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"HOME", "LANG", "LC_ALL", "PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR"}
        }
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "support_demo.mcp_server", "--data-dir", str(self.data_dir)],
            env=environment,
            cwd=Path(__file__).resolve().parent.parent,
        )
        async with asyncio.timeout(self.timeout):
            async with Client(server) as client:
                result = await client.call_tool(name, arguments)
        if result.is_error or not isinstance(result.structured_content, dict):
            raise SupportDataError("Support MCP returned invalid structured data.")
        return result.structured_content

    def list_users(self) -> list[dict[str, str]]:
        value = self._call("list_users", {}).get("users")
        if not isinstance(value, list) or not all(
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("name"), str)
            for item in value
        ):
            raise SupportDataError("Support MCP returned invalid users.")
        return value

    def get_user(self, user_id: str) -> dict[str, str]:
        value = self._call("get_user", {"user_id": user_id}).get("user")
        if (
            not isinstance(value, dict)
            or not all(isinstance(value.get(key), str) for key in ("id", "name", "source"))
            or value["id"] != user_id
        ):
            raise SupportDataError("Support MCP returned an invalid user.")
        return value

    def list_visible_tickets(self, user_id: str) -> list[dict[str, str]]:
        value = self._call("list_visible_tickets", {"user_id": user_id}).get("tickets")
        if not isinstance(value, list) or not all(
            isinstance(item, dict)
            and all(
                isinstance(item.get(key), str)
                for key in ("id", "scope", "title", "description", "status", "source")
            )
            and (
                item["scope"] == "global"
                or (item["scope"] == "personal" and item.get("user_id") == user_id)
            )
            for item in value
        ):
            raise SupportDataError("Support MCP returned invalid or unauthorized tickets.")
        return value
