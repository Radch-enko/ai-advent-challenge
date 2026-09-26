from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.services.task_state_machine import TaskStateMachine


@dataclass(frozen=True)
class TaskApiRuntime:
    mutation_lock: Callable[[str], Any]
    lifecycle_lock: Any
    get_session_locked: Callable[[str], ChatSession]
    has_active_task: Callable[[ChatSession], bool]
    sessions: SessionsRepository
    threadpool: Callable[..., Awaitable[Any]]
    start_worker: Callable[[str, str], None]
    task_state: Callable[[str, str], TaskState]
    task_active: Callable[[TaskState], bool]
    worker_running: Callable[[str, str], bool]
    recover_orphaned_task: Callable[[TaskState], None]
    session_task: Callable[[ChatSession, str], TaskState]
    checkpoint: Callable[..., ChatSession]
    state_machine: TaskStateMachine
