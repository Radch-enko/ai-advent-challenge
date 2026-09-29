from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpServiceBindings:
    _discover_connection: Callable[[], Any]
    _execute_resolved_tool: Callable[[], Any]
    _get_session: Callable[[], Any]
    _mcp_header: Callable[[], Any]
    _release_session_message_lock: Callable[[], Any]
    _resolved_mcp_tools: Callable[[], Any]
    _send_session_message_locked: Callable[[], Any]
    _session_message_lock: Callable[[], Any]
    artifact_store: Callable[[], Any]
    agents: Callable[[], Any]
    call_mcp_tool: Callable[[], Any]
    discover_mcp_tools: Callable[[], Any]
    mcp_connections: Callable[[], Any]
    profiles_path: Callable[[], Any]
    router: Callable[[], Any]
    run_in_threadpool: Callable[[], Any]
    sessions: Callable[[], Any]
