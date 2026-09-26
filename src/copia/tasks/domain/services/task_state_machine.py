from __future__ import annotations

from enum import StrEnum

from copia.tasks.domain.models.task_plan_step_status import TaskPlanStepStatus
from copia.tasks.domain.models.task_stage import TaskStage
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.models.task_status import TaskStatus


class TaskEvent(StrEnum):
    PLAN_CREATED = "plan_created"
    PLAN_APPROVED = "plan_approved"
    PLAN_CHANGES_REQUESTED = "plan_changes_requested"
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

    def apply(
        self,
        task: TaskState,
        event: TaskEvent,
        *,
        next_step: int | None = None,
        feedback: str | None = None,
    ) -> None:
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
        if event == TaskEvent.PLAN_APPROVED:
            if (
                task.stage != TaskStage.PLAN_REVIEW
                or task.status != TaskStatus.WAITING_FOR_APPROVAL
            ):
                raise InvalidTaskTransition("Only a plan awaiting approval can be approved")
            if task.plan is None:
                raise InvalidTaskTransition("Cannot approve a missing task plan")
            task.status = TaskStatus.RUNNING
            task.stage = TaskStage.EXECUTION
            task.current_step = 0
            task.expected_action = "Execute the current plan step"
            return
        if event == TaskEvent.PLAN_CHANGES_REQUESTED:
            if (
                task.stage != TaskStage.PLAN_REVIEW
                or task.status != TaskStatus.WAITING_FOR_APPROVAL
            ):
                raise InvalidTaskTransition("Plan changes can only be requested during plan review")
            if task.plan is None:
                raise InvalidTaskTransition("Cannot request changes for a missing task plan")
            if feedback is None or not feedback.strip():
                raise InvalidTaskTransition("Plan change feedback cannot be empty")
            task.status = TaskStatus.RUNNING
            task.stage = TaskStage.PLANNING
            task.current_step = None
            task.expected_action = "Revise the plan using the user's feedback"
            task.plan_feedback = feedback.strip()
            task.plan = None
            task.validation_result = None
            task.completion_report = None
            return
        if task.status not in {TaskStatus.RUNNING, TaskStatus.PAUSE_REQUESTED}:
            raise InvalidTaskTransition(f"Cannot apply {event} while task is {task.status}")

        if event == TaskEvent.PLAN_CREATED and task.stage == TaskStage.PLANNING:
            if task.plan is None:
                raise InvalidTaskTransition("Cannot review a missing task plan")
            task.stage = TaskStage.PLAN_REVIEW
            task.status = TaskStatus.WAITING_FOR_APPROVAL
            task.current_step = None
            task.expected_action = "Review the plan and approve it or request changes"
            return
        if event == TaskEvent.STEP_COMPLETED and task.stage == TaskStage.EXECUTION:
            if task.plan is None:
                raise InvalidTaskTransition("Cannot complete a step without a plan")
            if (
                task.current_step is None
                or task.current_step < 0
                or task.current_step >= len(task.plan.steps)
            ):
                raise InvalidTaskTransition("Execution checkpoint has no current plan step")
            if task.plan.steps[task.current_step].status != TaskPlanStepStatus.COMPLETED:
                raise InvalidTaskTransition("The current plan step must be completed first")
            expected_next_step = task.current_step + 1
            if next_step != expected_next_step:
                raise InvalidTaskTransition("Task steps must be completed sequentially")
            if next_step == len(task.plan.steps):
                task.stage = TaskStage.VALIDATION
                task.current_step = None
                task.expected_action = "Validate all completed plan steps"
            else:
                task.current_step = next_step
                task.expected_action = "Execute the current plan step"
            return
        if event == TaskEvent.VALIDATION_PASSED and task.stage == TaskStage.VALIDATION:
            self._require_complete_validation(task)
            task.stage = TaskStage.REPORT
            task.current_step = None
            task.expected_action = "Prepare the completion report"
            return
        if event == TaskEvent.VALIDATION_FAILED and task.stage == TaskStage.VALIDATION:
            task.status = TaskStatus.FAILED
            task.expected_action = None
            return
        if event == TaskEvent.REPORT_SAVED and task.stage == TaskStage.REPORT:
            self._require_complete_validation(task)
            if task.completion_report is None or not task.completion_report.strip():
                raise InvalidTaskTransition("Cannot finish a task without a completion report")
            task.stage = TaskStage.DONE
            task.status = TaskStatus.COMPLETED
            task.expected_action = None
            return
        raise InvalidTaskTransition(f"Invalid event {event} for stage {task.stage}")

    @staticmethod
    def _require_complete_validation(task: TaskState) -> None:
        validation = task.validation_result
        if validation is None or not validation.passed:
            raise InvalidTaskTransition("A task must pass validation before it can continue")
        if task.plan is None:
            raise InvalidTaskTransition("A validated task must have a plan")
        if any(step.status != TaskPlanStepStatus.COMPLETED for step in task.plan.steps):
            raise InvalidTaskTransition("Validation requires every plan step to be completed")
        expected_step_ids = {step.id for step in task.plan.steps}
        checked_step_ids = set(validation.checked_step_ids)
        if checked_step_ids != expected_step_ids:
            raise InvalidTaskTransition("Validation must cover every plan step exactly")

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
