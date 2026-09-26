from collections.abc import Callable
from typing import Any

from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.application.models.task_mcp_approval_runtime import TaskMcpApprovalRuntime
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.models.task_status import TaskStatus
from copia.tasks.domain.services.task_state_machine import TaskEvent, TaskStateMachine


class TaskMcpLifecycle:
    def __init__(
        self,
        get_checkpoint: Callable[..., ChatSession],
        get_session_task: Callable[[ChatSession, str], TaskState],
        get_approvals: Callable[[], dict[str, TaskMcpApprovalRuntime]],
        get_approvals_lock: Callable[[], Any],
        get_state_machine: Callable[[], TaskStateMachine],
    ) -> None:
        self._get_checkpoint = get_checkpoint
        self._get_session_task = get_session_task
        self._get_approvals = get_approvals
        self._get_approvals_lock = get_approvals_lock
        self._get_state_machine = get_state_machine

    def request_approval(self, session_id: str, task_id: str, approval: McpApproval) -> bool:
        runtime = TaskMcpApprovalRuntime(session_id=session_id, task_id=task_id, approval=approval)
        with self._get_approvals_lock():
            self._get_approvals()[approval.id] = runtime

        def waiting(session: ChatSession) -> None:
            task = self._get_session_task(session, task_id)
            task.status = TaskStatus.WAITING_FOR_APPROVAL
            task.expected_action = f"Approve or reject MCP tool {approval.tool_name}"
            task.mcp_approval = approval

        self._get_checkpoint()(session_id, waiting)
        runtime.event.wait()

        def resumed(session: ChatSession) -> None:
            task = self._get_session_task(session, task_id)
            task.status = TaskStatus.RUNNING
            task.expected_action = None
            task.mcp_approval = None

        self._get_checkpoint()(session_id, resumed)
        with self._get_approvals_lock():
            self._get_approvals().pop(approval.id, None)
        return bool(runtime.decision)

    def emit_event(
        self, session_id: str, task_id: str, event_type: str, data: dict[str, Any]
    ) -> None:
        if event_type not in {"tool_running", "tool_completed"}:
            return

        def update(session: ChatSession) -> None:
            task = self._get_session_task(session, task_id)
            task.mcp_running_tool = (
                str(data.get("tool_name")) if event_type == "tool_running" else None
            )

        self._get_checkpoint()(session_id, update)

    def pause_if_requested(self, session_id: str, task_id: str) -> bool:
        def update(session: ChatSession) -> None:
            task = self._get_session_task(session, task_id)
            if task.status == TaskStatus.PAUSE_REQUESTED:
                self._get_state_machine().apply(task, TaskEvent.PAUSED)
                task.recovered = True

        session = self._get_checkpoint()(session_id, update, revision=False)
        return self._get_session_task(session, task_id).status != TaskStatus.RUNNING
