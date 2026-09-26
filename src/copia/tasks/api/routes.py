from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.api.models.task_mode_update import TaskModeUpdate
from copia.tasks.api.models.task_plan_feedback_request import TaskPlanFeedbackRequest
from copia.tasks.api.models.task_start_request import TaskStartRequest
from copia.tasks.api.task_api_runtime import TaskApiRuntime
from copia.tasks.domain.models.task_stage import TaskStage
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.models.task_status import TaskStatus
from copia.tasks.domain.services.task_state_machine import InvalidTaskTransition, TaskEvent


class TaskRoutes:
    def __init__(self, runtime: Callable[[], TaskApiRuntime]) -> None:
        self._runtime = runtime

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/task-mode",
            self.update_session_task_mode,
            methods=["PATCH"],
            response_model=ChatSession,
        )
        router.add_api_route(
            "/sessions/{session_id}/tasks",
            self.start_task,
            methods=["POST"],
            response_model=TaskState,
            status_code=status.HTTP_202_ACCEPTED,
        )
        router.add_api_route(
            "/sessions/{session_id}/tasks/{task_id}",
            self.get_task,
            methods=["GET"],
            response_model=TaskState,
        )
        router.add_api_route(
            "/sessions/{session_id}/tasks/{task_id}/approve-plan",
            self.approve_task_plan,
            methods=["POST"],
            response_model=TaskState,
            status_code=status.HTTP_202_ACCEPTED,
        )
        router.add_api_route(
            "/sessions/{session_id}/tasks/{task_id}/request-plan-changes",
            self.request_task_plan_changes,
            methods=["POST"],
            response_model=TaskState,
            status_code=status.HTTP_202_ACCEPTED,
        )
        router.add_api_route(
            "/sessions/{session_id}/tasks/{task_id}/pause",
            self.pause_task,
            methods=["POST"],
            response_model=TaskState,
        )
        router.add_api_route(
            "/sessions/{session_id}/tasks/{task_id}/resume",
            self.resume_task,
            methods=["POST"],
            response_model=TaskState,
        )
        router.add_api_route(
            "/sessions/{session_id}/tasks/{task_id}/retry",
            self.retry_task,
            methods=["POST"],
            response_model=TaskState,
            status_code=status.HTTP_202_ACCEPTED,
        )
        return router

    async def update_session_task_mode(
        self, session_id: str, request: TaskModeUpdate
    ) -> ChatSession:
        runtime = self._runtime()

        def update() -> ChatSession:
            with runtime.mutation_lock(session_id):
                session = runtime.get_session_locked(session_id)
                if runtime.has_active_task(session):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Task mode cannot be changed while a task is active",
                    )
                session.task_mode_enabled = request.enabled
                session.updated_at = datetime.now(UTC)
                runtime.sessions.save(session)
                return session

        return await runtime.threadpool(update)

    async def start_task(self, session_id: str, request: TaskStartRequest) -> TaskState:
        runtime = self._runtime()

        def create() -> TaskState:
            with runtime.mutation_lock(session_id):
                session = runtime.get_session_locked(session_id)
                if not session.task_mode_enabled:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Task mode is disabled for this session",
                    )
                if runtime.has_active_task(session):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A task is already active for this session",
                    )
                now = datetime.now(UTC)
                task = TaskState(
                    id=str(uuid.uuid4()),
                    original_instruction=request.instruction,
                    stage=TaskStage.PLANNING,
                    status=TaskStatus.RUNNING,
                    expected_action="Create a plan for the task",
                    created_at=now,
                    updated_at=now,
                )
                session.messages.append(
                    ChatMessage(
                        role="user",
                        content=request.instruction,
                        created_at=now,
                        task_id=task.id,
                    )
                )
                session.task = task
                session.tasks.append(task)
                session.updated_at = now
                runtime.sessions.save(session)
                return task

        task = await runtime.threadpool(create)
        runtime.start_worker(session_id, task.id)
        return task

    async def get_task(self, session_id: str, task_id: str) -> TaskState:
        runtime = self._runtime()
        task = await runtime.threadpool(runtime.task_state, session_id, task_id)
        if (
            runtime.task_active(task)
            and task.status not in {TaskStatus.PAUSED, TaskStatus.WAITING_FOR_APPROVAL}
            and not runtime.worker_running(session_id, task_id)
        ):

            def recover(session: ChatSession) -> None:
                runtime.recover_orphaned_task(runtime.session_task(session, task_id))

            recovered_session = await runtime.threadpool(runtime.checkpoint, session_id, recover)
            task = runtime.session_task(recovered_session, task_id)
        return task

    async def approve_task_plan(self, session_id: str, task_id: str) -> TaskState:
        runtime = self._runtime()

        def approve() -> TaskState:
            with runtime.lifecycle_lock:
                session = runtime.get_session_locked(session_id)
                task = runtime.session_task(session, task_id)
                try:
                    runtime.state_machine.apply(task, TaskEvent.PLAN_APPROVED)
                except InvalidTaskTransition as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                task.recovered = False
                task.updated_at = datetime.now(UTC)
                session.updated_at = task.updated_at
                runtime.sessions.save(session)
                return task

        task = await runtime.threadpool(approve)
        runtime.start_worker(session_id, task_id)
        return task

    async def request_task_plan_changes(
        self, session_id: str, task_id: str, request: TaskPlanFeedbackRequest
    ) -> TaskState:
        runtime = self._runtime()

        def request_changes() -> TaskState:
            with runtime.lifecycle_lock:
                session = runtime.get_session_locked(session_id)
                task = runtime.session_task(session, task_id)
                try:
                    runtime.state_machine.apply(
                        task,
                        TaskEvent.PLAN_CHANGES_REQUESTED,
                        feedback=request.feedback,
                    )
                except InvalidTaskTransition as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                task.recovered = False
                task.updated_at = datetime.now(UTC)
                session.updated_at = task.updated_at
                runtime.sessions.save(session)
                return task

        task = await runtime.threadpool(request_changes)
        runtime.start_worker(session_id, task_id)
        return task

    async def pause_task(self, session_id: str, task_id: str) -> TaskState:
        runtime = self._runtime()

        def pause() -> TaskState:
            with runtime.lifecycle_lock:
                session = runtime.get_session_locked(session_id)
                task = runtime.session_task(session, task_id)
                if task.status == TaskStatus.PAUSED:
                    return task
                try:
                    runtime.state_machine.apply(task, TaskEvent.PAUSE_REQUESTED)
                except InvalidTaskTransition as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                task.updated_at = datetime.now(UTC)
                session.updated_at = task.updated_at
                runtime.sessions.save(session)
                return task

        return await runtime.threadpool(pause)

    async def resume_task(self, session_id: str, task_id: str) -> TaskState:
        runtime = self._runtime()

        def resume() -> TaskState:
            with runtime.lifecycle_lock:
                session = runtime.get_session_locked(session_id)
                task = runtime.session_task(session, task_id)
                try:
                    runtime.state_machine.apply(task, TaskEvent.RESUME)
                except InvalidTaskTransition as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                task.recovered = False
                task.updated_at = datetime.now(UTC)
                session.updated_at = task.updated_at
                runtime.sessions.save(session)
                return task

        task = await runtime.threadpool(resume)
        runtime.start_worker(session_id, task_id)
        return task

    async def retry_task(self, session_id: str, task_id: str) -> TaskState:
        runtime = self._runtime()

        def retry() -> TaskState:
            with runtime.lifecycle_lock:
                session = runtime.get_session_locked(session_id)
                task = runtime.session_task(session, task_id)
                try:
                    runtime.state_machine.apply(task, TaskEvent.RETRY_EXECUTION)
                except InvalidTaskTransition as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                session.messages = [
                    message
                    for message in session.messages
                    if not (message.task_id == task_id and message.task_step_id is not None)
                ]
                task.updated_at = datetime.now(UTC)
                session.updated_at = task.updated_at
                runtime.sessions.save(session)
                return task

        task = await runtime.threadpool(retry)
        runtime.start_worker(session_id, task_id)
        return task
