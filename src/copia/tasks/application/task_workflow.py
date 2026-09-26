import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from copia.agent_logs.domain.services.agent_log_context import agent_log_turn
from copia.common.domain.services.runtime_context import with_current_datetime_context
from copia.mcp.domain.services.mcp_tool_loop import McpToolLoop
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.application.task_workflow_runtime import TaskWorkflowRuntime
from copia.tasks.domain.models._planner_response import _PlannerResponse
from copia.tasks.domain.models.task_llm_call_status import TaskLlmCallStatus
from copia.tasks.domain.models.task_plan import TaskPlan
from copia.tasks.domain.models.task_plan_step import TaskPlanStep
from copia.tasks.domain.models.task_plan_step_status import TaskPlanStepStatus
from copia.tasks.domain.models.task_stage import TaskStage
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.models.task_status import TaskStatus
from copia.tasks.domain.models.task_validation_result import TaskValidationResult
from copia.tasks.domain.services import task_text
from copia.tasks.domain.services.task_state_machine import InvalidTaskTransition, TaskEvent


class TaskWorkflow:
    def __init__(self, get_runtime: Callable[[], TaskWorkflowRuntime]) -> None:
        self._get_runtime = get_runtime

    async def complete_call(
        self,
        session_id: str,
        task_id: str,
        *,
        stage: TaskStage,
        kind: str,
        step_id: str | None,
        messages: list[ChatMessage],
        config: LLMConfig,
    ) -> LLMResponse:
        runtime = self._get_runtime()
        agent_log_id = runtime.task_call_start(
            session_id, task_id=task_id, stage=stage, kind=kind, step_id=step_id
        )
        try:
            session = await runtime.get_session(session_id)
            resolved_tools = (
                await runtime.resolve_tools(session.config) if session.config.mcp_access else []
            )
            completion = None
            if resolved_tools:
                tool_loop = McpToolLoop(
                    runtime.router,
                    resolved_tools,
                    request_approval=lambda approval: runtime.request_mcp_approval(
                        session_id, task_id, approval
                    ),
                    execute=runtime.execute_tool,
                    emit=lambda event_type, data: runtime.emit_mcp_event(
                        session_id, task_id, event_type, data
                    ),
                    audit=lambda entry: runtime.agent_logs.append_tool_call(agent_log_id, entry),
                )
                completion = tool_loop.complete
            with agent_log_turn(
                session_id,
                agent_log_id,
                provider=config.provider,
                model=config.model,
                operation=kind,
            ):
                response = await runtime.threadpool(
                    completion or runtime.router.complete,
                    with_current_datetime_context(messages),
                    config,
                )
        except Exception as error:
            runtime.task_call_finish(
                session_id,
                agent_log_id,
                task_id=task_id,
                status_value=TaskLlmCallStatus.FAILED,
                error=str(error),
            )
            runtime.finish_log(
                agent_log_id,
                provider=config.provider,
                model=config.model,
                status="failed",
                error=kind,
            )
            raise
        runtime.task_call_finish(
            session_id,
            agent_log_id,
            task_id=task_id,
            status_value=TaskLlmCallStatus.COMPLETED,
        )
        runtime.finish_log(
            agent_log_id,
            provider=response.provider,
            model=response.model,
            usage=response.usage,
            status="completed",
        )
        return response

    async def run_task(self, session_id: str, task_id: str) -> None:
        runtime = self._get_runtime()
        try:
            while True:
                task = await runtime.threadpool(runtime.task_state, session_id, task_id)
                if task.status != TaskStatus.RUNNING:
                    return
                if task.stage == TaskStage.PLANNING:
                    await self.run_planning(session_id, task_id, task)
                elif task.stage == TaskStage.EXECUTION:
                    await self.run_execution(session_id, task_id, task)
                elif task.stage == TaskStage.VALIDATION:
                    await self.run_validation(session_id, task_id, task)
                elif task.stage == TaskStage.REPORT:
                    await self.run_report(session_id, task_id, task)
                else:
                    return
                if await runtime.threadpool(runtime.pause_if_requested, session_id, task_id):
                    return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            error_message = str(error)
            try:

                def fail(session: ChatSession) -> None:
                    assert session.task is not None
                    if session.task.id == task_id:
                        if (
                            session.task.stage == TaskStage.EXECUTION
                            and session.task.plan is not None
                            and session.task.current_step is not None
                        ):
                            step = session.task.plan.steps[session.task.current_step]
                            step.status = TaskPlanStepStatus.FAILED
                            step.error = error_message
                        runtime.state_machine.apply(session.task, TaskEvent.ERROR)
                        session.task.expected_action = error_message

                await runtime.threadpool(runtime.checkpoint, session_id, fail)
            except (runtime.http_error_type, OSError, ValueError, InvalidTaskTransition):
                pass
        finally:
            current = asyncio.current_task()
            if current is not None:
                runtime.finish_worker(session_id, current)

    async def run_planning(self, session_id: str, task_id: str, task: TaskState) -> None:
        runtime = self._get_runtime()
        session = await runtime.get_session(session_id)
        assert session.task is not None
        config = runtime.task_llm_config(session, structured_schema=runtime.plan_schema())
        response = await self.complete_call(
            session_id,
            task_id,
            stage=TaskStage.PLANNING,
            kind="task_planning",
            step_id=None,
            messages=runtime.system_messages(session, "You are the Copia task planner.")
            + [runtime.prompt_message(task_text._task_plan_payload(task))],
            config=config,
        )
        planned = _PlannerResponse.model_validate(response.structured_data)
        plan = TaskPlan(
            steps=[
                TaskPlanStep(
                    id=f"step-{index}",
                    order=index,
                    title=step.title,
                    instruction=step.instruction,
                    success_criteria=step.success_criteria,
                )
                for index, step in enumerate(planned.steps, start=1)
            ]
        )

        def save_plan(latest: ChatSession) -> None:
            assert latest.task is not None
            if latest.task.id != task_id:
                raise runtime.unknown_task_error()
            latest.task.plan = plan
            runtime.state_machine.apply(latest.task, TaskEvent.PLAN_CREATED)

        await runtime.threadpool(runtime.checkpoint, session_id, save_plan)

    async def run_execution(self, session_id: str, task_id: str, task: TaskState) -> None:
        runtime = self._get_runtime()
        if task.plan is None or task.current_step is None:
            raise ValueError("Execution checkpoint is missing the current plan step")
        step_index = task.current_step
        if step_index >= len(task.plan.steps):
            raise ValueError("Execution checkpoint points outside the plan")
        step = task.plan.steps[step_index]
        if step.status == TaskPlanStepStatus.COMPLETED:
            next_step = step_index + 1

            def advance(latest: ChatSession) -> None:
                assert latest.task is not None
                runtime.state_machine.apply(
                    latest.task, TaskEvent.STEP_COMPLETED, next_step=next_step
                )

            await runtime.threadpool(runtime.checkpoint, session_id, advance)
            return

        session = await runtime.get_session(session_id)
        config = runtime.task_llm_config(session)

        def mark_step_running(latest: ChatSession) -> None:
            assert latest.task is not None and latest.task.plan is not None
            latest.task.plan.steps[step_index].status = TaskPlanStepStatus.RUNNING

        await runtime.threadpool(runtime.checkpoint, session_id, mark_step_running)
        response = await self.complete_call(
            session_id,
            task_id,
            stage=TaskStage.EXECUTION,
            kind="task_execution_step",
            step_id=step.id,
            messages=runtime.system_messages(session, "You are the Copia task executor.")
            + [runtime.prompt_message(task_text._task_execution_payload(task, step))],
            config=config,
        )
        latest_task = await runtime.threadpool(runtime.task_state, session_id, task_id)
        execution_log_id = next(
            call.agent_log_id
            for call in reversed(latest_task.llm_calls)
            if call.kind == "task_execution_step" and call.step_id == step.id
        )

        def save_step(latest: ChatSession) -> None:
            current_task = runtime.session_task(latest, task_id)
            assert current_task.plan is not None
            current = current_task.plan.steps[step_index]
            current.status = TaskPlanStepStatus.COMPLETED
            current.result = response.content
            current.error = None
            runtime.state_machine.apply(
                current_task,
                TaskEvent.STEP_COMPLETED,
                next_step=step_index + 1,
            )
            latest.messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    created_at=datetime.now(UTC),
                    usage=response.usage,
                    context_window=response.context_window,
                    agent_log_id=execution_log_id,
                    task_id=task_id,
                    task_step_id=current.id,
                )
            )

        await runtime.threadpool(runtime.checkpoint, session_id, save_step)

    async def run_validation(self, session_id: str, task_id: str, task: TaskState) -> None:
        runtime = self._get_runtime()
        session = await runtime.get_session(session_id)
        invariants = await runtime.threadpool(runtime.invariants.load)
        config = runtime.task_llm_config(session, structured_schema=runtime.validation_schema())
        response = await self.complete_call(
            session_id,
            task_id,
            stage=TaskStage.VALIDATION,
            kind="task_validation",
            step_id=None,
            messages=runtime.system_messages(
                session,
                "You are the Copia task validator.",
                invariants=invariants,
            )
            + [runtime.prompt_message(task_text._task_validation_payload(task, invariants))],
            config=config,
        )
        validation = task_text._finalize_task_validation(
            TaskValidationResult.model_validate(response.structured_data),
            invariants,
            expected_step_ids={step.id for step in task.plan.steps} if task.plan else None,
        )

        def save_validation(latest: ChatSession) -> None:
            assert latest.task is not None
            latest.task.validation_result = validation
            runtime.state_machine.apply(
                latest.task,
                TaskEvent.VALIDATION_PASSED if validation.passed else TaskEvent.VALIDATION_FAILED,
            )

        await runtime.threadpool(runtime.checkpoint, session_id, save_validation)

    async def run_report(self, session_id: str, task_id: str, task: TaskState) -> None:
        runtime = self._get_runtime()
        session = await runtime.get_session(session_id)
        config = runtime.task_llm_config(session)
        response: LLMResponse | None = None
        for attempt in range(task_text.TASK_REPORT_MAX_ATTEMPTS):
            report_payload = task_text._task_report_payload(task)
            if attempt > 0:
                report_payload += (
                    "\n\nThis is a format correction attempt. The previous report was rejected "
                    "because its headings did not exactly match the required template. "
                    "Return exactly these three headings and no other Markdown headings: "
                    + ", ".join(task_text.TASK_REPORT_SECTIONS)
                    + ". Preserve the useful answer content, but do not add any heading "
                    "starting with # outside those three headings."
                )
            response = await self.complete_call(
                session_id,
                task_id,
                stage=TaskStage.REPORT,
                kind="task_report",
                step_id=None,
                messages=runtime.system_messages(
                    session, "You are the Copia completion report writer."
                )
                + [runtime.prompt_message(report_payload)],
                config=config,
            )
            if task_text._valid_task_report(response.content):
                break
        else:
            raise ValueError("Report does not match the required template")

        assert response is not None
        latest_task = await runtime.threadpool(runtime.task_state, session_id, task_id)
        report_log_id = next(
            call.agent_log_id
            for call in reversed(latest_task.llm_calls)
            if call.kind == "task_report"
        )

        def save_report(latest: ChatSession) -> None:
            assert latest.task is not None
            latest.task.completion_report = response.content
            latest.messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    created_at=datetime.now(UTC),
                    usage=response.usage,
                    context_window=response.context_window,
                    agent_log_id=report_log_id,
                    task_id=task_id,
                )
            )
            runtime.state_machine.apply(latest.task, TaskEvent.REPORT_SAVED)

        await runtime.threadpool(runtime.checkpoint, session_id, save_report)

    def start_worker(self, session_id: str, task_id: str) -> None:
        runtime = self._get_runtime()
        with runtime.workers_lock:
            existing = runtime.workers.get(session_id)
            if existing is not None and not existing.done():

                async def start_after_previous() -> None:
                    try:
                        await existing
                    except asyncio.CancelledError:
                        return
                    with runtime.workers_lock:
                        current = runtime.workers.get(session_id)
                        if current is not None and not current.done():
                            return
                        worker = asyncio.create_task(self.run_task(session_id, task_id))
                        runtime.workers[session_id] = worker

                asyncio.create_task(start_after_previous())
                return
            worker = asyncio.create_task(self.run_task(session_id, task_id))
            runtime.workers[session_id] = worker
