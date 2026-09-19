from datetime import UTC, datetime

from copia.api import service
from copia.domain.models.invariant import Invariant
from copia.domain.models.task import (
    TaskPlan,
    TaskPlanStep,
    TaskPlanStepStatus,
    TaskStage,
    TaskState,
    TaskStatus,
    TaskValidationResult,
)


def invariant(item_id: str = "weekends") -> Invariant:
    now = datetime.now(UTC)
    return Invariant(
        id=item_id,
        name="Weekend work",
        text="Never schedule work on weekends",
        created_at=now,
        updated_at=now,
    )


def test_task_validation_fails_when_llm_reports_invariant_issue() -> None:
    result = service._finalize_task_validation(
        TaskValidationResult(
            passed=True,
            issues=[],
            checked_step_ids=["step-1"],
            checked_invariant_ids=["weekends"],
            invariant_issues=["The plan schedules work on Saturday"],
        ),
        [invariant()],
    )

    assert result.passed is False
    assert result.invariant_issues == ["The plan schedules work on Saturday"]
    assert result.issues == ["Invariant validation: The plan schedules work on Saturday"]


def test_task_validation_fails_when_llm_does_not_check_every_invariant() -> None:
    result = service._finalize_task_validation(
        TaskValidationResult(
            passed=True,
            issues=[],
            checked_step_ids=["step-1"],
            checked_invariant_ids=[],
            invariant_issues=[],
        ),
        [invariant()],
    )

    assert result.passed is False
    assert result.invariant_issues == ["Invariant was not checked: Weekend work (weekends)"]
    assert result.issues == [
        "Invariant validation: Invariant was not checked: Weekend work (weekends)"
    ]


def test_task_validation_payload_lists_invariants() -> None:
    now = datetime.now(UTC)
    task = TaskState(
        id="task-1",
        original_instruction="Finish the task this week",
        stage=TaskStage.VALIDATION,
        status=TaskStatus.RUNNING,
        plan=TaskPlan(
            steps=[
                TaskPlanStep(
                    id="step-1",
                    order=1,
                    title="Complete the work",
                    instruction="Complete the work during weekdays",
                    success_criteria="Work is complete",
                    status=TaskPlanStepStatus.COMPLETED,
                    result="Completed",
                )
            ]
        ),
        created_at=now,
        updated_at=now,
    )

    payload = service._task_validation_payload(task, [invariant()])

    assert "checked_invariant_ids" in payload
    assert "invariant_issues" in payload
    assert "weekends: Weekend work" in payload
    assert "Never schedule work on weekends" in payload
