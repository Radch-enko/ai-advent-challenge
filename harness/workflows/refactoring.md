# Refactoring Workflow

## Use When

Changing structure while preserving behavior.

## Purpose

Improve structure while preserving behavior.

## Required Inputs

- Behavioral invariants.
- Scope and affected modules.
- Rollback plan.

## Task Matching

Before using any task from `docs/tasks/active/`, compare its goal, scope, affected area, and acceptance criteria with the current user request.

- If it clearly matches, use it as the authoritative task specification.
- If it does not match, ignore it for the current run. Do not inherit its acceptance criteria, constraints, scope, or verification commands; use the current user request as task context or create a new task specification through `harness/workflows/task-authoring.md`.
- If the match is ambiguous, record the ambiguity instead of silently adopting the task. Prefer creating a new task context when the user request is sufficiently detailed.

## Procedure

1. Define behavior that must remain unchanged.
2. Capture before-change verification evidence.
3. Plan the smallest structural change.
4. Avoid opportunistic feature work.
5. Implement in small steps.
6. Apply `harness/workflows/test-integrity-gate.md` if tests changed:
   - new tests are allowed automatically;
   - existing test modifications require a Test Change Report before review continues;
   - existing test deletions require explicit human approval before implementation continues.
7. Run the same focused checks before and after when practical.
8. Run `./harness/scripts/check.sh`.
9. Report before-and-after evidence.

## Required Checks

- Before-and-after focused verification where practical.
- `./harness/scripts/check.sh`.

## Prohibited Behavior

- Opportunistic user-visible changes.
- Module boundary changes without explicit approval.
- Changing existing tests without Test Integrity Gate justification.

## Completion Criteria

Behavior is demonstrably unchanged, scope stayed bounded, and rollback is clear.

## Output

Report changed structure, invariant evidence, commands, and rollback notes.
