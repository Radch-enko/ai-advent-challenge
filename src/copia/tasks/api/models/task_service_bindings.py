from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskServiceBindings:
    _execute_resolved_tool: Callable[[], Any]
    _finish_agent_log: Callable[[], Any]
    _get_session: Callable[[], Any]
    _get_session_locked: Callable[[], Any]
    _recover_orphaned_task: Callable[[], Any]
    _request_task_mcp_approval: Callable[[], Any]
    _resolved_mcp_tools: Callable[[], Any]
    _session_mutation_lock: Callable[[], Any]
    _session_task: Callable[[], Any]
    _start_task_worker: Callable[[], Any]
    _task_call_finish: Callable[[], Any]
    _task_call_start: Callable[[], Any]
    _task_checkpoint: Callable[[], Any]
    _task_plan_schema: Callable[[], Any]
    _task_system_messages: Callable[[], Any]
    _task_validation_schema: Callable[[], Any]
    agent_log_store: Callable[[], Any]
    invariants_repository: Callable[[], Any]
    router: Callable[[], Any]
    run_in_threadpool: Callable[[], Any]
    session_lifecycle_lock: Callable[[], Any]
    sessions: Callable[[], Any]
    task_mcp_approvals: Callable[[], Any]
    task_mcp_approvals_lock: Callable[[], Any]
    task_state_machine: Callable[[], Any]
    task_workers: Callable[[], Any]
    task_workers_lock: Callable[[], Any]
