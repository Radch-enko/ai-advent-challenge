# Task Authoring Workflow

## Use When

Turning an informal request into a complete task specification under `docs/tasks/active/` or `docs/tasks/backlog/`.

## Purpose

Create a scoped, testable task specification without modifying production code.

## Required Inputs

- Informal request.
- `AGENTS.md`.
- Repository assessment and relevant product or architecture docs.
- `harness/templates/task.md`.

## Procedure

1. Identify goal and context.
2. Inspect actual repository modules related to the request.
3. State assumptions.
4. Capture functional and non-functional requirements.
5. Define out-of-scope behavior.
6. Write testable acceptance criteria.
7. Identify relevant modules and files.
8. Confirm verification commands exist before listing them.
9. List risks and open questions.
10. Save the task file in the requested task directory.

## Required Checks

- Confirm commands exist before listing them as required verification.

## Prohibited Behavior

- Silently expanding ambiguous scope.
- Inventing modules or tools.
- Modifying production code.

## Output

A task file using `harness/templates/task.md`.
