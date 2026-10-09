from copia.common.domain.services.prompt_resources import load_prompt, render_prompt
from copia.invariants.domain.models.invariant import Invariant
from copia.tasks.domain.models.task_plan_step import TaskPlanStep
from copia.tasks.domain.models.task_plan_step_status import TaskPlanStepStatus
from copia.tasks.domain.models.task_state import TaskState
from copia.tasks.domain.models.task_validation_result import TaskValidationResult

TASK_REPORT_SECTIONS = (
    "## Итоговый ответ",
    "### Детали",
    "### Ограничения",
)
TASK_REPORT_MAX_ATTEMPTS = 2
TASK_ROLE_PROMPTS = {
    role: load_prompt("copia.tasks", f"{role}_role.md")
    for role in ("planner", "executor", "validator", "report_writer")
}


def report_correction_prompt() -> str:
    return render_prompt(
        "copia.tasks",
        "report_correction.md",
        headings=", ".join(TASK_REPORT_SECTIONS),
    )


def _task_plan_payload(task: TaskState) -> str:
    feedback = (
        "\n\n" + render_prompt("copia.tasks", "plan_feedback.md", feedback=task.plan_feedback)
        if task.plan_feedback
        else ""
    )
    return render_prompt(
        "copia.tasks",
        "plan_payload.md",
        task=task.original_instruction,
        feedback=feedback,
    )


def _task_execution_payload(task: TaskState, step: TaskPlanStep) -> str:
    assert task.plan is not None
    previous = "\n".join(
        f"{item.order}. {item.title}: {item.result or item.error or item.status}"
        for item in task.plan.steps
        if item.status == TaskPlanStepStatus.COMPLETED
    )
    validation_feedback = ""
    if task.validation_result is not None and not task.validation_result.passed:
        issues = "\n".join(f"- {issue}" for issue in task.validation_result.issues)
        validation_feedback = "\n\n" + render_prompt(
            "copia.tasks",
            "validation_feedback.md",
            issues=issues or load_prompt("copia.tasks", "validation_feedback_empty.md"),
        )
    return render_prompt(
        "copia.tasks",
        "execution_payload.md",
        task=task.original_instruction,
        order=str(step.order),
        title=step.title,
        instruction=step.instruction,
        success_criteria=step.success_criteria,
        previous=previous or "Нет",
        validation_feedback=validation_feedback,
    )


def _task_validation_payload(task: TaskState, invariants: list[Invariant]) -> str:
    assert task.plan is not None
    steps = "\n".join(
        f"{step.id}: {step.title}\nРезультат: {step.result or step.error or 'Нет результата'}\n"
        f"Критерии: {step.success_criteria}"
        for step in task.plan.steps
    )
    invariant_items = "\n".join(
        f"{item.id}: {item.name}\nОграничение: {item.text}" for item in invariants
    )
    return render_prompt(
        "copia.tasks",
        "validation_payload.md",
        task=task.original_instruction,
        steps=steps,
        invariants=invariant_items or "Нет",
    )


def _finalize_task_validation(
    validation: TaskValidationResult,
    invariants: list[Invariant],
    expected_step_ids: set[str] | None = None,
) -> TaskValidationResult:
    step_issues: list[str] = []
    if expected_step_ids is not None:
        checked_step_ids = set(validation.checked_step_ids)
        missing_step_ids = sorted(expected_step_ids - checked_step_ids)
        unknown_step_ids = sorted(checked_step_ids - expected_step_ids)
        if missing_step_ids:
            step_issues.append("Steps were not checked: " + ", ".join(missing_step_ids))
        if unknown_step_ids:
            step_issues.append(
                "Validation referenced unknown step IDs: " + ", ".join(unknown_step_ids)
            )

    expected_ids = {item.id for item in invariants}
    checked_ids = set(validation.checked_invariant_ids)
    missing = [item for item in invariants if item.id not in checked_ids]
    unknown_ids = sorted(checked_ids - expected_ids)
    invariant_issues = list(validation.invariant_issues)
    issues = list(validation.issues)

    for issue in step_issues:
        if issue not in issues:
            issues.append(issue)

    for item in missing:
        invariant_issues.append(f"Invariant was not checked: {item.name} ({item.id})")
    if unknown_ids:
        invariant_issues.append(
            "Validation referenced unknown invariant IDs: " + ", ".join(unknown_ids)
        )

    for issue in invariant_issues:
        formatted = f"Invariant validation: {issue}"
        if formatted not in issues:
            issues.append(formatted)

    return validation.model_copy(
        update={
            "passed": validation.passed and not invariant_issues and not step_issues,
            "issues": issues,
            "invariant_issues": invariant_issues,
        }
    )


def _task_report_payload(task: TaskState) -> str:
    assert task.plan is not None
    steps = "\n".join(
        f"{step.order}. {step.title} — {step.status}\nРезультат: {step.result or '—'}"
        for step in task.plan.steps
    )
    validation = task.validation_result
    checked = ", ".join(validation.checked_step_ids) if validation else "—"
    issues = "; ".join(validation.issues) if validation and validation.issues else "Нет"
    return render_prompt(
        "copia.tasks",
        "report_payload.md",
        task=task.original_instruction,
        steps=steps,
        checked=checked,
        issues=issues,
    )


def _valid_task_report(report: str) -> bool:
    headings = [line.strip() for line in report.splitlines() if line.strip().startswith("#")]
    return headings == list(TASK_REPORT_SECTIONS)
