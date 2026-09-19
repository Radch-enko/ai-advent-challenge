# Отчёт Test Integrity

## Резюме

- Task: Add invariant validation to task mode
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: `tests/test_task_api.py`, `tests/test_task_retry.py`
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `MERGED`

## Обоснование

- Reason Category: `ACCEPTANCE_CRITERIA_CHANGED`
- Why The Test Changed: The task validation contract now requires the separate validation LLM request to report checked invariants and invariant violations in addition to step success criteria.
- Old Expected Behavior: Task validation returned `passed`, `issues`, and `checked_step_ids` and considered only step success criteria.
- New Expected Behavior: Task validation also returns `checked_invariant_ids` and `invariant_issues`; invariant violations or incomplete invariant coverage fail validation.
- Affected Acceptance Criteria: Task mode must reject completed work that violates a configured global invariant and expose the reason through validation issues.
- Specification Changed: `YES`
- Incorrect Artifact: `UNCLEAR`

## Согласование удаления

- Existing Test Deleted: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`
- Approval Evidence: Not applicable.

## Оценка ревьюера

- Is The Justification Valid: `YES`
- Does The Test Still Protect The Same Behavior: `YES`
- Was Production Code Incorrectly Avoided: `NO`
- Should Production Code Have Been Fixed Instead: `NO`
- Notes: The validation contract intentionally changed. Existing fakes provide the new required structured-output fields, and no assertions were removed or weakened. New tests cover reported violations, incomplete invariant coverage, and invariant payload rendering.

## Evidence

- Diff Evidence: Existing task validation tests retain their original pipeline and retry assertions while adding the required invariant fields; a new test file covers invariant-specific behavior.
- Verification Commands: `./.venv/bin/pytest -q tests/test_task_api.py tests/test_task_retry.py tests/test_task_invariant_validation.py`; `env COPIA_SESSIONS_PATH=/private/tmp/copia-day14-task-validation-sessions-3 COPIA_MEMORY_PATH=/private/tmp/copia-day14-task-validation-memory-3 COPIA_INVARIANTS_PATH=/private/tmp/copia-day14-task-validation-invariants-3.json ./harness/scripts/check.sh`.
- Related Production Changes: `src/copia/domain/models/task.py`, `src/copia/api/service.py`, and `client/src/domain/models/task.ts`.
