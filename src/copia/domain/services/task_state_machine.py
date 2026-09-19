from __future__ import annotations

from enum import StrEnum

from ..models.task import TaskPlanStepStatus, TaskStage, TaskState, TaskStatus


class TaskEvent(StrEnum):
    PLAN_CREATED = "plan_created"
    STEP_COMPLETED = "step_completed"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    RETRY_EXECUTION = "retry_execution"
    REPORT_SAVED = "report_saved"
    ERROR = "error"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    RESUME = "resume"


class InvalidTaskTransition(ValueError):
    pass


class TaskStateMachine:
    """The only component allowed to advance a persisted task state."""

    def apply(self, task: TaskState, event: TaskEvent, *, next_step: int | None = None) -> None:
        if event == TaskEvent.PAUSE_REQUESTED:
            self._pause_requested(task)
            return
        if event == TaskEvent.PAUSED:
            self._paused(task)
            return
        if event == TaskEvent.RESUME:
            self._resume(task)
            return
        if event == TaskEvent.ERROR:
            if task.stage in {TaskStage.DONE} or task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
            }:
                raise InvalidTaskTransition("A finished task cannot fail")
            task.status = TaskStatus.FAILED
            task.expected_action = None
            return
        if event == TaskEvent.RETRY_EXECUTION:
            if task.status != TaskStatus.FAILED or task.stage != TaskStage.VALIDATION:
                raise InvalidTaskTransition("Only a failed validation stage can be retried")
            if task.plan is None:
                raise InvalidTaskTransition("Cannot retry validation without a task plan")
            task.status = TaskStatus.RUNNING
            task.stage = TaskStage.EXECUTION
            task.current_step = 0
            task.expected_action = "Execute the current plan step using validation feedback"
            for step in task.plan.steps:
                step.status = TaskPlanStepStatus.PENDING
                step.result = None
                step.error = None
            task.recovered = False
            return
        if task.status not in {TaskStatus.RUNNING, TaskStatus.PAUSE_REQUESTED}:
            raise InvalidTaskTransition(f"Cannot apply {event} while task is {task.status}")

        if event == TaskEvent.PLAN_CREATED and task.stage == TaskStage.PLANNING:
            task.stage = TaskStage.EXECUTION
            task.current_step = 0
            task.expected_action = "Execute the current plan step"
            return
        if event == TaskEvent.STEP_COMPLETED and task.stage == TaskStage.EXECUTION:
            if task.plan is None:
                raise InvalidTaskTransition("Cannot complete a step without a plan")
            if next_step is None or next_step >= len(task.plan.steps):
                task.stage = TaskStage.VALIDATION
                task.current_step = None
                task.expected_action = "Validate all completed plan steps"
            else:
                task.current_step = next_step
                task.expected_action = "Execute the current plan step"
            return
        if event == TaskEvent.VALIDATION_PASSED and task.stage == TaskStage.VALIDATION:
            task.stage = TaskStage.REPORT
            task.current_step = None
            task.expected_action = "Prepare the completion report"
            return
        if event == TaskEvent.VALIDATION_FAILED and task.stage == TaskStage.VALIDATION:
            task.status = TaskStatus.FAILED
            task.expected_action = None
            return
        if event == TaskEvent.REPORT_SAVED and task.stage == TaskStage.REPORT:
            task.stage = TaskStage.DONE
            task.status = TaskStatus.COMPLETED
            task.expected_action = None
            return
        raise InvalidTaskTransition(f"Invalid event {event} for stage {task.stage}")

    def _pause_requested(self, task: TaskState) -> None:
        if task.stage == TaskStage.DONE or task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            raise InvalidTaskTransition("A finished task cannot be paused")
        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.PAUSE_REQUESTED
            return
        if task.status != TaskStatus.PAUSE_REQUESTED:
            raise InvalidTaskTransition(f"Cannot request pause while task is {task.status}")

    def _paused(self, task: TaskState) -> None:
        if task.status != TaskStatus.PAUSE_REQUESTED:
            raise InvalidTaskTransition("A pause must be requested before it is confirmed")
        task.status = TaskStatus.PAUSED

    def _resume(self, task: TaskState) -> None:
        if task.status != TaskStatus.PAUSED:
            raise InvalidTaskTransition(f"Cannot resume task while task is {task.status}")
        task.status = TaskStatus.RUNNING
