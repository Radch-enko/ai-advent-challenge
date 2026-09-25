from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..models.config import (
    ChatMessage,
    LLMConfig,
    LLMResponse,
    ToolCall,
    ToolDefinition,
    ToolLoopMessage,
)
from ..models.mcp import McpApproval
from .router import LLMRouter
from .runtime_context import with_current_datetime_context

MAX_TOOL_CALLS_PER_TURN = 8


class McpToolLoopError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedMcpTool:
    alias: str
    connection_id: str
    connection_name: str
    tool_name: str
    definition: ToolDefinition


@dataclass(frozen=True)
class ToolExecutionResult:
    content: str
    is_error: bool = False


def provider_tool_alias(connection_id: str, tool_name: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9_-]+", "_", f"mcp_{connection_id}_{tool_name}").strip("_")
    digest = hashlib.sha256(f"{connection_id}\0{tool_name}".encode()).hexdigest()[:10]
    prefix = readable[: 64 - len(digest) - 1] or "mcp"
    return f"{prefix}_{digest}"


class McpToolLoop:
    def __init__(
        self,
        router: LLMRouter,
        tools: list[ResolvedMcpTool],
        request_approval: Callable[[McpApproval], bool],
        execute: Callable[[ResolvedMcpTool, dict[str, Any]], ToolExecutionResult],
        emit: Callable[[str, dict[str, Any]], None],
        audit: Callable[[dict[str, Any]], None] | None = None,
        prepare_arguments: Callable[[ResolvedMcpTool, dict[str, Any]], dict[str, Any]]
        | None = None,
        max_tool_calls: int = MAX_TOOL_CALLS_PER_TURN,
    ) -> None:
        self._router = router
        self._tools = {tool.alias: tool for tool in tools}
        self._request_approval = request_approval
        self._execute = execute
        self._emit = emit
        self._audit = audit or (lambda _: None)
        self._prepare_arguments = prepare_arguments or (lambda _tool, arguments: arguments)
        if max_tool_calls < 1:
            raise ValueError("MCP tool call limit must be positive")
        self._max_tool_calls = max_tool_calls

    def complete(self, messages: list[ChatMessage], config: LLMConfig) -> LLMResponse:
        conversation: list[ChatMessage | ToolLoopMessage] = list(messages)
        definitions = [tool.definition for tool in self._tools.values()]
        call_count = 0
        while True:
            response = self._router.complete(
                with_current_datetime_context(conversation), config, definitions
            )
            if not response.tool_calls:
                return response
            conversation.append(
                ToolLoopMessage(
                    role="assistant", content=response.content, tool_calls=response.tool_calls
                )
            )
            for call in response.tool_calls:
                call_count += 1
                if call_count > self._max_tool_calls:
                    raise McpToolLoopError("MCP tool call limit exceeded")
                result = self._handle_call(call)
                conversation.append(
                    ToolLoopMessage(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.id,
                        content=result.content,
                    )
                )

    def _handle_call(self, call: ToolCall) -> ToolExecutionResult:
        tool = self._tools.get(call.name)
        if tool is None:
            raise McpToolLoopError("Provider requested an unavailable MCP tool")
        arguments = self._prepare_arguments(tool, call.arguments)
        approval = McpApproval(
            id=call.id,
            connection_id=tool.connection_id,
            connection_name=tool.connection_name,
            tool_name=tool.tool_name,
            arguments=arguments,
        )
        self._emit("tool_approval_required", approval.model_dump(mode="json"))
        approved = self._request_approval(approval)
        if not approved:
            result = ToolExecutionResult("User rejected this tool call", is_error=True)
            self._audit(
                {
                    "connection_id": tool.connection_id,
                    "tool_name": tool.tool_name,
                    "arguments": arguments,
                    "decision": "rejected",
                    "status": "skipped",
                    "result": result.content,
                    "duration_seconds": 0,
                }
            )
            return result
        self._emit("tool_running", {**approval.model_dump(mode="json"), "decision": "approved"})
        started = time.monotonic()
        try:
            result = self._execute(tool, arguments)
        except Exception as error:
            duration = time.monotonic() - started
            self._audit(
                {
                    "connection_id": tool.connection_id,
                    "tool_name": tool.tool_name,
                    "arguments": arguments,
                    "decision": "approved",
                    "status": "failed",
                    "result": str(error)[:1000],
                    "duration_seconds": duration,
                }
            )
            raise
        duration = time.monotonic() - started
        audit = {
            "connection_id": tool.connection_id,
            "tool_name": tool.tool_name,
            "arguments": arguments,
            "decision": "approved",
            "status": "completed",
            "result": result.content,
            "duration_seconds": duration,
        }
        self._audit(audit)
        self._emit("tool_completed", audit)
        return result


def encode_tool_result(value: object, *, limit: int = 2 * 1024 * 1024) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > limit:
        raise McpToolLoopError("MCP tool result exceeds the allowed size")
    return encoded
