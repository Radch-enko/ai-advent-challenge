from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_llm_call import TaskLlmCall
from copia.tasks.domain.models.task_llm_call_status import TaskLlmCallStatus
from copia.tasks.domain.models.task_stage import TaskStage
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.services.task_state_rules import session_tasks


class TaskStateAccess:
    def __init__(
        self,
        get_sessions: Callable[[], SessionsRepository],
        get_lifecycle_lock: Callable[[], Any],
        get_agent_logs: Callable[[], AgentLogStore],
        get_session_task: Callable[[ChatSession, str], TaskState],
        get_checkpoint: Callable[..., ChatSession],
        unknown_task_error: Callable[[], Exception],
        unknown_session_error: Callable[[], Exception],
        get_workers: Callable[[], dict[str, asyncio.Task[None]]],
        get_workers_lock: Callable[[], Any],
    ) -> None:
        self._get_sessions = get_sessions
        self._get_lifecycle_lock = get_lifecycle_lock
        self._get_agent_logs = get_agent_logs
        self._get_session_task = get_session_task
        self._get_checkpoint = get_checkpoint
        self._unknown_task_error = unknown_task_error
        self._unknown_session_error = unknown_session_error
        self._get_workers = get_workers
        self._get_workers_lock = get_workers_lock

    def checkpoint(
        self, session_id: str, update: Callable[[ChatSession], None], *, revision: bool = True
    ) -> ChatSession:
        """Сохраняет короткое изменение без удержания блокировки вызова провайдера."""
        with self._get_lifecycle_lock():
            sessions = self._get_sessions()
            session = sessions.load(session_id)
            if session is None or session.task is None:
                raise self._unknown_task_error()
            update(session)
            if revision:
                session.task.checkpoint_revision += 1
            session.task.updated_at = datetime.now(UTC)
            session.updated_at = session.task.updated_at
            sessions.save(session)
            return session

    def task_state(self, session_id: str, task_id: str) -> TaskState:
        with self._get_lifecycle_lock():
            session = self._get_sessions().load(session_id)
        if session is None:
            raise self._unknown_session_error()
        return self._get_session_task(session, task_id)

    def session_task(self, session: ChatSession, task_id: str) -> TaskState:
        task = next((item for item in session_tasks(session) if item.id == task_id), None)
        if task is None:
            raise self._unknown_task_error()
        return task

    def worker_running(self, session_id: str, task_id: str) -> bool:
        with self._get_workers_lock():
            worker = self._get_workers().get(session_id)
            return worker is not None and not worker.done()

    def finish_worker(self, session_id: str, worker: asyncio.Task[None]) -> None:
        with self._get_workers_lock():
            workers = self._get_workers()
            if workers.get(session_id) is worker:
                workers.pop(session_id, None)

    def call_start(
        self,
        session_id: str,
        *,
        task_id: str,
        stage: TaskStage,
        kind: str,
        step_id: str | None,
    ) -> str:
        agent_log_id = self._get_agent_logs().start_turn(session_id)
        now = datetime.now(UTC)

        def update(session: ChatSession) -> None:
            task = self._get_session_task(session, task_id)
            task.llm_calls.append(
                TaskLlmCall(
                    agent_log_id=agent_log_id,
                    stage=stage,
                    kind=kind,
                    step_id=step_id,
                    provider=session.config.provider,
                    model=session.config.model,
                    status=TaskLlmCallStatus.RUNNING,
                    started_at=now,
                )
            )

        self._get_checkpoint()(session_id, update)
        return agent_log_id

    def call_finish(
        self,
        session_id: str,
        agent_log_id: str,
        *,
        task_id: str,
        status_value: TaskLlmCallStatus,
        error: str | None = None,
    ) -> ChatSession:
        finished_at = datetime.now(UTC)

        def update(session: ChatSession) -> None:
            task = self._get_session_task(session, task_id)
            call = next(
                (item for item in task.llm_calls if item.agent_log_id == agent_log_id),
                None,
            )
            if call is None:
                raise ValueError("Task LLM call is missing")
            call.status = status_value
            call.completed_at = finished_at
            call.duration_seconds = max(0, (finished_at - call.started_at).total_seconds())
            call.error = error

        return self._get_checkpoint()(session_id, update)
