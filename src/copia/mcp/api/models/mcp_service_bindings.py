from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpServiceBindings:
    _discover_connection: Callable[[], Any]
    _emit_turn: Callable[[], Any]
    _execute_resolved_tool: Callable[[], Any]
    _get_session: Callable[[], Any]
    _mcp_header: Callable[[], Any]
    _persist_mcp_turn_state: Callable[[], Any]
    _release_session_message_lock: Callable[[], Any]
    _resolved_mcp_tools: Callable[[], Any]
    _run_mcp_turn: Callable[[], Any]
    _send_session_message_locked: Callable[[], Any]
    _session_message_lock: Callable[[], Any]
    _turn_approval: Callable[[], Any]
    agent_log_store: Callable[[], Any]
    agents: Callable[[], Any]
    call_mcp_tool: Callable[[], Any]
    discover_mcp_tools: Callable[[], Any]
    mcp_connections: Callable[[], Any]
    mcp_turn_workers: Callable[[], Any]
    mcp_turns: Callable[[], Any]
    mcp_turns_lock: Callable[[], Any]
    profiles_path: Callable[[], Any]
    router: Callable[[], Any]
    run_in_threadpool: Callable[[], Any]
    session_lifecycle_lock: Callable[[], Any]
    sessions: Callable[[], Any]
    task_mcp_approvals: Callable[[], Any]
    task_mcp_approvals_lock: Callable[[], Any]
