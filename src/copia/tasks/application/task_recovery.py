from collections.abc import Callable
from datetime import UTC, datetime

from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.models.task_status import TaskStatus


class TaskRecovery:
    def __init__(
        self,
        get_sessions: Callable[[], SessionsRepository],
        session_tasks: Callable[[ChatSession], list[TaskState]],
        task_active: Callable[[TaskState], bool],
        worker_running: Callable[[str, str], bool],
        recover_task: Callable[[TaskState], None],
    ) -> None:
        self._get_sessions = get_sessions
        self._session_tasks = session_tasks
        self._task_active = task_active
        self._worker_running = worker_running
        self._recover_task = recover_task

    def recover_session_tasks(self, session_id: str, session: ChatSession) -> None:
        orphaned_tasks = [
            task
            for task in self._session_tasks(session)
            if self._task_active(task)
            and task.status not in {TaskStatus.PAUSED, TaskStatus.WAITING_FOR_APPROVAL}
            and not self._worker_running(session_id, task.id)
        ]
        if not orphaned_tasks:
            return
        for task in orphaned_tasks:
            self._recover_task(task)
        session.updated_at = datetime.now(UTC)
        self._get_sessions().save(session)
