import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from copia.mcp.domain.services.mcp_tool_loop import (
    ResolvedMcpTool,
    ToolExecutionResult,
    encode_tool_result,
)


class ExpenseSummaryPager:
    def __init__(
        self,
        period_from: datetime,
        period_to: datetime,
        execute_tool: Callable[[ResolvedMcpTool, dict[str, Any]], ToolExecutionResult],
    ) -> None:
        self.period_from = period_from
        self.upper = period_to - timedelta(microseconds=1)
        self._execute_tool = execute_tool
        self.expected_cursor: str | None = None
        self.called = False
        self.finished = False
        self.expense_count = 0

    def prepare(self, _tool: ResolvedMcpTool, arguments: dict[str, Any]) -> dict[str, Any]:
        cursor = arguments.get("cursor")
        if (
            self.finished
            or cursor != self.expected_cursor
            or (cursor is not None and not isinstance(cursor, str))
        ):
            raise RuntimeError("Unexpected expense page cursor")
        actual = {
            "occurred_from": self.period_from.astimezone(UTC).isoformat(),
            "occurred_to": self.upper.astimezone(UTC).isoformat(),
            "page_size": 100,
        }
        if cursor is not None:
            actual["cursor"] = cursor
        return actual

    def execute(self, tool: ResolvedMcpTool, arguments: dict[str, Any]) -> ToolExecutionResult:
        result = self._execute_tool(tool, arguments)
        self.called = True
        if result.is_error:
            raise RuntimeError("Expense search MCP tool returned an error")
        try:
            payload = json.loads(result.content)
            page = payload["structured_content"]
            items = page["items"]
            next_cursor = page["next_cursor"]
            if not isinstance(items, list) or not (
                next_cursor is None or isinstance(next_cursor, str) and next_cursor
            ):
                raise ValueError("Invalid expense page")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("Expense search MCP tool returned an invalid page") from error
        self.expected_cursor = next_cursor
        self.finished = next_cursor is None
        self.expense_count += len(items)
        return ToolExecutionResult(
            encode_tool_result({"expense_count": len(items), "structured_content": page})
        )
