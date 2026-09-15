# Test Integrity Gate

## Purpose

Make every modification of an existing test explicit, reviewable, and evidence-based. The gate does not forbid changing
tests; it separates justified specification/test corrections from changes that hide production defects.

## Risk Levels

| Change | Risk | Gate action |
| --- | --- | --- |
| Create a new test file or add a new test case without weakening existing assertions | Low | Allowed automatically. No Test Change Report is required. |
| Modify an existing test file | Medium | Stop implementation flow and create a Test Change Report before review continues. |
| Delete an existing test file or remove an existing test case/assertion without replacement | High | Stop implementation flow, explain the requested deletion, and ask for explicit human approval. Without approval, implementation remains blocked. |

Disabling, ignoring, commenting out, narrowing, or weakening an existing test counts as modifying or deleting the test
coverage it previously provided.

## Existing Test Detection

Use the task base revision, branch base, or pre-change worktree snapshot as the reference point.

- A test path present in the reference and changed in the diff is an existing test modification.
- A test path present in the reference and absent after the change is an existing test deletion.
- A newly added test path is low risk unless it also replaces, disables, or removes existing coverage.

When Git metadata is available, inspect the diff with commands such as:

```bash
git diff --name-status
git diff -- 'tests/**' 'client/src/**/*.test.ts' 'client/src/**/*.test.tsx'
```

## Required Justification

For every medium-risk existing test modification, create a Test Change Report under:

```text
docs/reports/test-integrity/
```

Use `harness/templates/test-integrity-report.md`. The report must include:

- changed test files;
- risk level;
- controlled reason category;
- why the test changed;
- old expected behavior;
- new expected behavior;
- affected acceptance criteria;
- whether the specification changed;
- whether production code or the test was incorrect;
- reviewer verdict;
- final outcome.

Allowed reason categories:

- `SPECIFICATION_CHANGED`
- `ACCEPTANCE_CRITERIA_CHANGED`
- `TEST_BUG`
- `FLAKY_TEST`
- `IMPLEMENTATION_DETAIL_TO_BEHAVIOR`
- `EXPANDED_COVERAGE`
- `REFACTORING_NO_BEHAVIOR_CHANGE`

Do not use "because the test failed" as a justification. A failing test is evidence to investigate, not a reason to
change the test.

## Acceptance Criteria Linkage

When acceptance criteria have stable identifiers, cite those identifiers in the report. When they do not, use the
nearest task checkbox, requirement text, or `not individually tracked` plus a short description. Keep the field shape so
future AC identifiers can be added without redesigning the report.

## Human Approval For Deletions

If an existing test is deleted or existing coverage is removed without replacement:

1. Stop implementation.
2. Record the file, test name when known, old behavior protected, reason deletion is requested, and safer alternatives considered.
3. Ask the human for explicit approval.
4. Continue only after approval is recorded in the Test Change Report.

## Review Gate

When existing tests were modified, review must explicitly answer:

- Is the justification valid?
- Does the test still protect the same behavior?
- Was production code incorrectly avoided?
- Should production code have been fixed instead?

The reviewer verdict must be one of:

- `APPROVED`
- `APPROVED_WITH_NOTES`
- `REJECTED`

If the verdict is `REJECTED`, implementation returns to the implementer before completion.
