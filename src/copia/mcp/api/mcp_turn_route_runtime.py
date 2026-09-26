import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime
from copia.tasks.application.models.task_mcp_approval_runtime import TaskMcpApprovalRuntime


@dataclass(frozen=True)
class McpTurnRouteRuntime:
    get_session: Callable[[str], Awaitable[Any]]
    threadpool: Callable[..., Awaitable[Any]]
    persist_turn: Callable[..., None]
    emit_turn: Callable[[McpTurnRuntime, str, dict[str, Any]], None]
    run_turn: Callable[..., Awaitable[None]]
    turns: dict[str, McpTurnRuntime]
    turns_lock: Any
    workers: dict[str, asyncio.Task[None]]
    task_approvals: dict[str, TaskMcpApprovalRuntime]
    task_approvals_lock: Any
