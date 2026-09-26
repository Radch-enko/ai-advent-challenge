import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agents.domain.models.agent_config import AgentConfig
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.providers.application.llm_router import LLMRouter
from copia.providers.domain.models.llm_config import LLMConfig
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.services.task_state_machine import TaskStateMachine


@dataclass(frozen=True)
class TaskWorkflowRuntime:
    task_call_start: Callable[..., str]
    task_call_finish: Callable[..., ChatSession]
    get_session: Callable[[str], Awaitable[ChatSession]]
    resolve_tools: Callable[[AgentConfig], Awaitable[list[ResolvedMcpTool]]]
    request_mcp_approval: Callable[[str, str, McpApproval], bool]
    execute_tool: Callable[[ResolvedMcpTool, dict[str, Any]], ToolExecutionResult]
    emit_mcp_event: Callable[..., None]
    agent_logs: AgentLogStore
    router: LLMRouter
    threadpool: Callable[..., Awaitable[Any]]
    finish_log: Callable[..., None]
    task_state: Callable[..., TaskState]
    pause_if_requested: Callable[..., bool]
    checkpoint: Callable[..., ChatSession]
    finish_worker: Callable[..., None]
    task_llm_config: Callable[..., LLMConfig]
    plan_schema: Callable[[], dict[str, object]]
    system_messages: Callable[..., list[ChatMessage]]
    prompt_message: Callable[[str], ChatMessage]
    validation_schema: Callable[[], dict[str, object]]
    invariants: InvariantsRepository
    session_task: Callable[[ChatSession, str], TaskState]
    state_machine: TaskStateMachine
    workers_lock: Any
    workers: dict[str, asyncio.Task[None]]
    unknown_task_error: Callable[[], Exception]
    http_error_type: type[Exception]
