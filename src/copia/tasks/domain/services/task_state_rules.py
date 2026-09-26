from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.models.task_status import TaskStatus
from copia.tasks.domain.services.task_state_machine import TaskEvent, TaskStateMachine


def session_tasks(session: ChatSession) -> list[TaskState]:
    if session.tasks:
        return session.tasks
    return [session.task] if session.task is not None else []


def task_active(task: TaskState | None) -> bool:
    return task is not None and task.status in {
        TaskStatus.RUNNING,
        TaskStatus.PAUSE_REQUESTED,
        TaskStatus.PAUSED,
        TaskStatus.WAITING_FOR_APPROVAL,
    }


def session_has_active_task(session: ChatSession) -> bool:
    return any(task_active(task) for task in session_tasks(session))


def recover_orphaned_task(task: TaskState, state_machine: TaskStateMachine) -> None:
    if task.mcp_approval is not None or task.mcp_running_tool is not None:
        task.status = TaskStatus.FAILED
        task.expected_action = "Retry the task after an interrupted MCP tool call"
        task.mcp_approval = None
        task.mcp_running_tool = None
        task.recovered = True
        return
    if task.status == TaskStatus.RUNNING:
        state_machine.apply(task, TaskEvent.PAUSE_REQUESTED)
    if task.status == TaskStatus.PAUSE_REQUESTED:
        state_machine.apply(task, TaskEvent.PAUSED)
    task.recovered = True
    task.expected_action = "Resume the task to continue from the saved checkpoint"
