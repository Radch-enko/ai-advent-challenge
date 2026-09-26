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


def _task_plan_payload(task: TaskState) -> str:
    feedback = (
        "\n\nUser feedback on the previous plan:\n" + task.plan_feedback
        if task.plan_feedback
        else ""
    )
    return (
        "Create an actionable plan for the task below. Return only the structured output. "
        "Use a small number of independent, sequential steps.\n\n"
        f"Task:\n{task.original_instruction}"
        f"{feedback}"
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
        validation_feedback = (
            "\n\nValidation feedback from the previous attempt:\n"
            f"{issues or '- Rework the result against every success criterion.'}\n"
            "Use this feedback to improve the current step."
        )
    return (
        "Execute exactly the current task step. Do not execute another step and do not change "
        "the task stage. Return a concise result that can be checked later.\n\n"
        f"Original task:\n{task.original_instruction}\n\n"
        f"Current step ({step.order}): {step.title}\n"
        f"Instruction: {step.instruction}\n"
        f"Success criteria: {step.success_criteria}\n\n"
        f"Previous completed results:\n{previous or 'None'}"
        f"{validation_feedback}"
    )


def _task_validation_payload(task: TaskState, invariants: list[Invariant]) -> str:
    assert task.plan is not None
    steps = "\n".join(
        f"{step.id}: {step.title}\nResult: {step.result or step.error or 'No result'}\n"
        f"Criteria: {step.success_criteria}"
        for step in task.plan.steps
    )
    invariant_items = "\n".join(
        f"{item.id}: {item.name}\nConstraint: {item.text}" for item in invariants
    )
    return (
        "Validate the completed task against every success criterion and every invariant. "
        "Return only structured output with passed, issues, checked_step_ids, "
        "checked_invariant_ids, and invariant_issues. Add a concise explanation to "
        "invariant_issues for each violated invariant.\n\n"
        f"Original task:\n{task.original_instruction}\n\n{steps}"
        f"\n\nInvariants to check:\n{invariant_items or 'None'}"
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
        f"{step.order}. {step.title} — {step.status}\nResult: {step.result or '—'}"
        for step in task.plan.steps
    )
    validation = task.validation_result
    checked = ", ".join(validation.checked_step_ids) if validation else "—"
    issues = "; ".join(validation.issues) if validation and validation.issues else "Нет"
    return (
        "Prepare the user-facing final answer using exactly the required Russian headings. "
        "The answer must focus on the result for the original user request, not on the "
        "internal task workflow. Do not describe planning, execution stages, validation "
        "statuses, API logs, or subtask progress. Return plain text only; do not use JSON, "
        "code fences, or add headings outside the template.\n\n"
        "Required template:\n"
        "## Итоговый ответ\n\n"
        "[Direct answer to the user's request. Start with the result.]\n\n"
        "### Детали\n\n"
        "[Only important details needed to understand or use the answer.]\n\n"
        "### Ограничения\n\n"
        "[Only limitations that affect the answer, or Нет.]\n\n"
        f"Original user request:\n{task.original_instruction}\n\n"
        f"Internal execution results (use as context, do not reproduce the workflow):\n{steps}\n\n"
        f"Internal validation context (do not expose statuses):\nChecked steps: {checked}\n"
        f"Validation issues: {issues}"
    )


def _valid_task_report(report: str) -> bool:
    headings = [line.strip() for line in report.splitlines() if line.strip().startswith("#")]
    return headings == list(TASK_REPORT_SECTIONS)
