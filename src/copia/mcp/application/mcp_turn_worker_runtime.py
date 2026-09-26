import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime
from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.providers.application.llm_router import LLMRouter


@dataclass(frozen=True)
class McpTurnWorkerRuntime:
    message_lock: Callable[[str], Any]
    release_message_lock: Callable[[Any], None]
    threadpool: Callable[..., Awaitable[Any]]
    background_factory: Callable[[], Any]
    get_session: Callable[[str], Awaitable[Any]]
    resolve_tools: Callable[[AgentConfig], Awaitable[list[ResolvedMcpTool]]]
    router: LLMRouter
    turn_approval: Callable[[McpTurnRuntime, McpApproval], bool]
    execute_tool: Callable[[ResolvedMcpTool, dict[str, Any]], ToolExecutionResult]
    emit_turn: Callable[[McpTurnRuntime, str, dict[str, Any]], None]
    send_locked: Callable[..., Awaitable[Any]]
    agent_logs: AgentLogStore
    persist_turn: Callable[..., None]
    turns_lock: Any
    workers: dict[str, asyncio.Task[None]]
    sanitize_error: Callable[[str], str]
