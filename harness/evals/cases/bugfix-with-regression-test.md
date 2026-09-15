---
id: bugfix-with-regression-test
title: Fix blank chat message handling
task: Reject a blank chat message at the appropriate boundary and cover the behavior with a regression test where practical.
fixture: current repository
allowed_scope: affected Copia source and related tests only
forbidden_changes: provider selection, session persistence format, unrelated client redesign
expected_commands: ./harness/scripts/test.sh; ./harness/scripts/check.sh
deterministic_assertions: regression_test_or_rationale
hard_failure_conditions: production-only fix with no test rationale; unrelated UI redesign
---

The agent should reproduce or reason from the defect, isolate the state path, and avoid broad changes.
