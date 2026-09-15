# Review Workflow

## Use When

Reviewing a task plan, implementation diff, or completed agent work.

## Purpose

Independently review work for defects.

## Required Inputs

- Task and acceptance criteria.
- Diff or changed files.
- Verification claims.

## Priorities

1. Correctness.
2. Unmet requirements.
3. Regressions.
4. Security.
5. Concurrency and lifecycle.
6. Architecture boundaries.
7. Missing tests.
8. Unnecessary complexity.
9. Accidental unrelated changes.

## Procedure

1. Read the task, plan, and relevant architecture docs.
2. Inspect the diff and changed tests.
3. If existing tests were modified, apply `harness/workflows/test-integrity-gate.md`:
   - verify that a Test Change Report exists;
   - answer the Test Integrity Review questions;
   - produce `APPROVED`, `APPROVED_WITH_NOTES`, or `REJECTED`;
   - if rejected, return implementation to the implementer.
4. If an existing test was deleted, verify explicit human approval before approving the work.
5. Verify claims against files and command output.
6. Report concrete findings with severity and file references.
7. Include open questions and residual risk.

## Required Checks

- At minimum, inspect changed tests and related production code.
- For existing test modifications, inspect the Test Change Report and record a Test Integrity verdict.

## Prohibited Behavior

- Editing files unless explicitly requested.
- Style-only findings unless they affect maintainability or policy.

## Output

Use `harness/templates/review-report.md`. Review should be read-only unless edits are explicitly requested.
