from __future__ import annotations

from types import ModuleType
from typing import Self

from fastapi import HTTPException

from copia.invariants.domain.models.invariant import Invariant
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.api.models.task_service_bindings import TaskServiceBindings
from copia.tasks.api.task_api_runtime import TaskApiRuntime
from copia.tasks.application.task_mcp_lifecycle import TaskMcpLifecycle
from copia.tasks.application.task_recovery import TaskRecovery
from copia.tasks.application.task_state_access import TaskStateAccess
from copia.tasks.application.task_workflow import TaskWorkflow
from copia.tasks.application.task_workflow_runtime import TaskWorkflowRuntime
from copia.tasks.domain.models.task_llm_call_status import TaskLlmCallStatus
from copia.tasks.domain.models.task_stage import TaskStage
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.services import task_prompt, task_state_rules


class TaskServiceComposition:
    @classmethod
    def from_service(cls, service: ModuleType) -> Self:
        return cls(
            TaskServiceBindings(
                _execute_resolved_tool=lambda: service._execute_resolved_tool,
                _finish_agent_log=lambda: service._finish_agent_log,
                _get_session=lambda: service._get_session,
                _get_session_locked=lambda: service._get_session_locked,
                _recover_orphaned_task=lambda: service._recover_orphaned_task,
                _request_task_mcp_approval=lambda: service._request_task_mcp_approval,
                _resolved_mcp_tools=lambda: service._resolved_mcp_tools,
                _session_mutation_lock=lambda: service._session_mutation_lock,
                _session_task=lambda: service._session_task,
                _start_task_worker=lambda: service._start_task_worker,
                _task_call_finish=lambda: service._task_call_finish,
                _task_call_start=lambda: service._task_call_start,
                _task_checkpoint=lambda: service._task_checkpoint,
                _task_plan_schema=lambda: service._task_plan_schema,
                _task_system_messages=lambda: service._task_system_messages,
                _task_validation_schema=lambda: service._task_validation_schema,
                agent_log_store=lambda: service.agent_log_store,
                invariants_repository=lambda: service.invariants_repository,
                router=lambda: service.router,
                run_in_threadpool=lambda: service.run_in_threadpool,
                session_lifecycle_lock=lambda: service.session_lifecycle_lock,
                sessions=lambda: service.sessions,
                task_mcp_approvals=lambda: service.task_mcp_approvals,
                task_mcp_approvals_lock=lambda: service.task_mcp_approvals_lock,
                task_state_machine=lambda: service.task_state_machine,
                task_workers=lambda: service.task_workers,
                task_workers_lock=lambda: service.task_workers_lock,
            )
        )

    def __init__(self, bindings: TaskServiceBindings) -> None:
        self._bindings = bindings
        service = bindings
        self.state_access = TaskStateAccess(
            lambda: service.sessions(),
            lambda: service.session_lifecycle_lock(),
            lambda: service.agent_log_store(),
            lambda session, task_id: service._session_task()(session, task_id),
            lambda: service._task_checkpoint(),
            lambda: HTTPException(status_code=404, detail="Unknown task"),
            lambda: HTTPException(status_code=404, detail="Unknown session"),
            lambda: service.task_workers(),
            lambda: service.task_workers_lock(),
        )
        self.mcp_lifecycle = TaskMcpLifecycle(
            lambda: service._task_checkpoint(),
            lambda session, task_id: service._session_task()(session, task_id),
            lambda: service.task_mcp_approvals(),
            lambda: service.task_mcp_approvals_lock(),
            lambda: service.task_state_machine(),
        )
        self.workflow = TaskWorkflow(self.workflow_runtime)
        self.recovery = TaskRecovery(
            lambda: service.sessions(),
            task_state_rules.session_tasks,
            task_state_rules.task_active,
            self.state_access.worker_running,
            self.recover_orphaned_task,
        )

    def system_messages(
        self,
        session: ChatSession,
        role_prompt: str,
        invariants: list[Invariant] | None = None,
    ) -> list[ChatMessage]:
        return task_prompt.system_messages(
            session, role_prompt, invariants, self._bindings.invariants_repository().load
        )

    def checkpoint(self, session_id: str, update: object, *, revision: bool = True) -> ChatSession:
        return self.state_access.checkpoint(session_id, update, revision=revision)

    def session_task(self, session: ChatSession, task_id: str) -> TaskState:
        return self.state_access.session_task(session, task_id)

    def call_start(
        self,
        session_id: str,
        *,
        task_id: str,
        stage: TaskStage,
        kind: str,
        step_id: str | None,
    ) -> str:
        return self.state_access.call_start(
            session_id, task_id=task_id, stage=stage, kind=kind, step_id=step_id
        )

    def call_finish(
        self,
        session_id: str,
        agent_log_id: str,
        *,
        task_id: str,
        status_value: TaskLlmCallStatus,
        error: str | None = None,
    ) -> ChatSession:
        return self.state_access.call_finish(
            session_id, agent_log_id, task_id=task_id, status_value=status_value, error=error
        )

    def recover_orphaned_task(self, task: TaskState) -> None:
        task_state_rules.recover_orphaned_task(task, self._bindings.task_state_machine())

    def workflow_runtime(self) -> TaskWorkflowRuntime:
        service = self._bindings
        return TaskWorkflowRuntime(
            task_call_start=service._task_call_start(),
            task_call_finish=service._task_call_finish(),
            get_session=service._get_session(),
            resolve_tools=service._resolved_mcp_tools(),
            request_mcp_approval=service._request_task_mcp_approval(),
            execute_tool=service._execute_resolved_tool(),
            emit_mcp_event=self.mcp_lifecycle.emit_event,
            agent_logs=service.agent_log_store(),
            router=service.router(),
            threadpool=service.run_in_threadpool(),
            finish_log=service._finish_agent_log(),
            task_state=self.state_access.task_state,
            pause_if_requested=self.mcp_lifecycle.pause_if_requested,
            checkpoint=service._task_checkpoint(),
            finish_worker=self.state_access.finish_worker,
            task_llm_config=task_prompt.task_llm_config,
            plan_schema=service._task_plan_schema(),
            system_messages=service._task_system_messages(),
            prompt_message=task_prompt.prompt_message,
            validation_schema=service._task_validation_schema(),
            invariants=service.invariants_repository(),
            session_task=service._session_task(),
            state_machine=service.task_state_machine(),
            workers_lock=service.task_workers_lock(),
            workers=service.task_workers(),
            unknown_task_error=lambda: HTTPException(status_code=404, detail="Unknown task"),
            http_error_type=HTTPException,
        )

    def api_runtime(self) -> TaskApiRuntime:
        service = self._bindings
        return TaskApiRuntime(
            mutation_lock=service._session_mutation_lock(),
            lifecycle_lock=service.session_lifecycle_lock(),
            get_session_locked=service._get_session_locked(),
            has_active_task=task_state_rules.session_has_active_task,
            sessions=service.sessions(),
            threadpool=service.run_in_threadpool(),
            start_worker=service._start_task_worker(),
            task_state=self.state_access.task_state,
            task_active=task_state_rules.task_active,
            worker_running=self.state_access.worker_running,
            recover_orphaned_task=service._recover_orphaned_task(),
            session_task=service._session_task(),
            checkpoint=service._task_checkpoint(),
            state_machine=service.task_state_machine(),
        )
