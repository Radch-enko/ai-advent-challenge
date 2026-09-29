from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.agents.domain.models.agent import Agent
from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult


@dataclass(frozen=True)
class ExpenseSummaryRuntime:
    get_profile: Callable[[str], AgentConfig | None]
    resolve_tools: Callable[[AgentConfig], Awaitable[list[ResolvedMcpTool]]]
    execute_tool: Callable[[ResolvedMcpTool, dict[str, Any]], ToolExecutionResult]
    router: Any
    make_agent: Callable[..., Agent]
    sanitize_error: Callable[[str], str]
