# Bugfix Workflow

## Use When

Correcting broken, regressed, or surprising behavior.

## Purpose

Fix a defect with regression evidence.

## Required Inputs

- Reproduction steps or explicit failure evidence.
- Expected behavior.
- Affected module or user path, if known.

## Task Matching

Before using any task from `docs/tasks/active/`, compare its goal, scope, affected area, and acceptance criteria with the current user request.

- If it clearly matches, use it as the authoritative task specification.
- If it does not match, ignore it for the current run. Do not inherit its acceptance criteria, constraints, scope, or verification commands; use the current user request as task context or create a new task specification through `harness/workflows/task-authoring.md`.
- If the match is ambiguous, record the ambiguity instead of silently adopting the task. Prefer creating a new task context when the user request is sufficiently detailed.

## Procedure

1. Reproduce the failure or document why it cannot be reproduced.
2. Isolate root cause using the smallest relevant code path.
3. Add a regression test that fails before the fix when practical.
4. Make a minimal corrective change.
5. Apply `harness/workflows/test-integrity-gate.md` if tests changed:
   - new regression tests are allowed automatically;
   - existing test modifications require a Test Change Report before review continues;
   - existing test deletions require explicit human approval before implementation continues.
6. Check related behavior for similar regressions.
7. Run focused tests for the affected area.
8. Run `./harness/scripts/check.sh` when feasible.
9. Report root cause, fix, evidence, and residual risk.

## Required Checks

- Regression test or documented reason none was practical.
- `./harness/scripts/check.sh` when feasible.

## Prohibited Behavior

- Broad refactoring disguised as a fix.
- Suppressing the failure instead of fixing it.
- Changing existing tests without Test Integrity Gate justification.

## Completion Criteria

The defect is fixed, regression coverage exists or a reason is documented, and no unrelated behavior changed.

## Output

Report root cause, fix, commands, results, and residual risk.
