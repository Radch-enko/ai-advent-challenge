# Feature Workflow

## Use When

Adding small user-visible behavior or extending existing behavior without changing architecture.

## Purpose

Implement a small feature through the repository SDLC harness.

## Required Inputs

- Confirmed matching active task spec with testable acceptance criteria, or current user request plus task context
  created through the task-authoring workflow.
- `AGENTS.md`.
- Relevant product and architecture docs.
- Known constraints and out-of-scope items.
- Applicable policies in `harness/policies/`.
- `harness/workflows/test-integrity-gate.md` when tests are changed.

## Task Matching

Before using any task from `docs/tasks/active/`, compare its goal, scope, affected area, and acceptance criteria with
the current user request.

- If it clearly matches, use it as the authoritative task specification.
- If it does not match, ignore it for the current run. Do not inherit its acceptance criteria, constraints, scope, or
  verification commands; use the current user request as task context or create a new task specification through
  `harness/workflows/task-authoring.md`.
- If the match is ambiguous, record the ambiguity instead of silently adopting the task. Prefer creating a new task
  context when the user request is sufficiently detailed.

## Procedure

1. Establish task context.
2. Read relevant documentation and repository facts.
3. Create the implementation plan.
4. Implement the smallest change that satisfies the task.
5. Apply the Test Integrity Gate if tests changed:
   - new tests are allowed automatically;
   - existing test modifications require a Test Change Report before review continues;
   - existing test deletions require explicit human approval before implementation continues.
6. Self-review the diff for scope, architecture, tests, and hidden failures.
7. Run focused checks for affected modules or behavior.
8. Run `./harness/scripts/check.sh` when feasible.
9. Produce a completion report.

Stage order:

```text
Task context
-> Relevant documentation and repository facts
-> Implementation planning
-> Implementation
-> Review
-> Verification
```

## Required Checks

- Focused tests for affected code where available.
- `./harness/scripts/check.sh` or exact failure and limitation.

## Boundaries

- Do not introduce feature-to-feature dependencies.
- Keep backend/client contracts and provider-agnostic models consistent when integration changes.
- Do not rework UI, dependency wiring, or package structure unless required by the task.
- Do not redesign architecture without task scope.
- Do not hide failing checks.
- Do not modify existing tests without following `harness/workflows/test-integrity-gate.md`.

## Completion Criteria

Acceptance criteria are satisfied, verification evidence is recorded, no unrelated changes are present, and unresolved
risks are stated.

## Output

Use `harness/templates/completion-report.md`.
