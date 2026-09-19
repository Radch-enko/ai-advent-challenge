from datetime import UTC, datetime

import pytest

from copia.domain.models.task import (
    TaskPlan,
    TaskPlanStep,
    TaskPlanStepStatus,
    TaskStage,
    TaskState,
    TaskStatus,
    TaskValidationResult,
)
from copia.domain.services.task_state_machine import (
    InvalidTaskTransition,
    TaskEvent,
    TaskStateMachine,
)


def make_task() -> TaskState:
    return TaskState(
        id="task-1",
        original_instruction="Do the task",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_task_state_machine_enforces_pipeline_order() -> None:
    machine = TaskStateMachine()
    task = make_task()

    with pytest.raises(InvalidTaskTransition):
        machine.apply(task, TaskEvent.STEP_COMPLETED)
    task.plan = TaskPlan(
        steps=[
            TaskPlanStep(
                id="step-1",
                order=1,
                title="First",
                instruction="First",
                success_criteria="Done",
            ),
            TaskPlanStep(
                id="step-2",
                order=2,
                title="Second",
                instruction="Second",
                success_criteria="Done",
            ),
        ]
    )
    machine.apply(task, TaskEvent.PLAN_CREATED)
    assert task.stage == TaskStage.PLAN_REVIEW
    assert task.status == TaskStatus.WAITING_FOR_APPROVAL
    machine.apply(task, TaskEvent.PLAN_APPROVED)
    assert task.stage == TaskStage.EXECUTION
    assert task.current_step == 0

    assert task.plan is not None
    task.plan.steps[0].status = TaskPlanStepStatus.COMPLETED
    machine.apply(task, TaskEvent.STEP_COMPLETED, next_step=1)
    assert task.stage == TaskStage.EXECUTION
    assert task.current_step == 1
    task.plan.steps[1].status = TaskPlanStepStatus.COMPLETED
    machine.apply(task, TaskEvent.STEP_COMPLETED, next_step=2)
    assert task.stage == TaskStage.VALIDATION
    task.validation_result = TaskValidationResult(
        passed=True,
        issues=[],
        checked_step_ids=["step-1", "step-2"],
    )
    machine.apply(task, TaskEvent.VALIDATION_PASSED)
    assert task.stage == TaskStage.REPORT
    task.completion_report = "## Итоговый ответ\n\nDone"
    machine.apply(task, TaskEvent.REPORT_SAVED)
    assert task.stage == TaskStage.DONE
    assert task.status == TaskStatus.COMPLETED


def test_pause_is_orthogonal_and_preserves_stage_and_step() -> None:
    machine = TaskStateMachine()
    task = make_task()
    task.plan = TaskPlan(
        steps=[
            TaskPlanStep(
                id="step-1",
                order=1,
                title="First",
                instruction="First",
                success_criteria="Done",
            )
        ]
    )
    machine.apply(task, TaskEvent.PLAN_CREATED)
    machine.apply(task, TaskEvent.PLAN_APPROVED)
    machine.apply(task, TaskEvent.PAUSE_REQUESTED)
    machine.apply(task, TaskEvent.PAUSED)
    assert task.status == TaskStatus.PAUSED
    assert task.stage == TaskStage.EXECUTION
    assert task.current_step == 0
    machine.apply(task, TaskEvent.RESUME)
    assert task.status == TaskStatus.RUNNING


def test_failed_task_cannot_continue() -> None:
    machine = TaskStateMachine()
    task = make_task()
    machine.apply(task, TaskEvent.ERROR)
    assert task.status == TaskStatus.FAILED
    with pytest.raises(InvalidTaskTransition):
        machine.apply(task, TaskEvent.PLAN_CREATED)
