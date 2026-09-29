from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.domain.models.mcp_artifact import McpArtifact
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.providers.application.llm_router import LLMRouter
from copia.providers.domain.models.llm_response import LLMResponse


@dataclass(frozen=True)
class McpConversationWorkerRuntime:
    message_lock: Callable[[str], Any]
    release_message_lock: Callable[[Any], None]
    threadpool: Callable[..., Awaitable[Any]]
    background_factory: Callable[[], Any]
    get_session: Callable[[str], Awaitable[Any]]
    resolve_tools: Callable[[AgentConfig], Awaitable[list[ResolvedMcpTool]]]
    router: LLMRouter
    execute_tool: Callable[[ResolvedMcpTool, dict[str, Any]], ToolExecutionResult]
    publish_artifacts: Callable[[str, tuple[McpArtifact, ...]], tuple[str, ...]]
    finalize_response: Callable[[str, LLMResponse, tuple[McpArtifact, ...]], LLMResponse]
    send_locked: Callable[..., Awaitable[Any]]
    sanitize_error: Callable[[str], str]
    stream_completion: Callable[..., LLMResponse] | None = None
