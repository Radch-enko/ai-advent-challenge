# Test Integrity Report: Import-only module removal

## Summary

- Task: Remove import-only and re-export-only compatibility modules and update their consumers to canonical feature paths.
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files:
  - `tests/test_agent.py`
  - `tests/test_agent_log_final_reviewer_regressions.py`
  - `tests/test_agent_log_persistence.py`
  - `tests/test_agent_log_profile_name_sanitization.py`
  - `tests/test_agent_log_reviewer_regressions.py`
  - `tests/test_agent_log_url_redaction.py`
  - `tests/test_agent_logs.py`
  - `tests/test_credential_only_logging.py`
  - `tests/test_day11_blockers.py`
  - `tests/test_day11_context_contracts.py`
  - `tests/test_day11_delete_lifecycle.py`
  - `tests/test_day11_facts_redaction_and_context_race.py`
  - `tests/test_day11_final_fixes.py`
  - `tests/test_day11_final_security_fixes.py`
  - `tests/test_day11_latest_review_blockers.py`
  - `tests/test_day11_long_term_memory_toggle_race.py`
  - `tests/test_day11_memory_layers.py`
  - `tests/test_day11_retry_message_concurrency.py`
  - `tests/test_day11_review_findings.py`
  - `tests/test_day11_safe_fixes.py`
  - `tests/test_day11_session_message_concurrency.py`
  - `tests/test_day12_final_reviewer_regressions.py`
  - `tests/test_expense_search.py`
  - `tests/test_expenses.py`
  - `tests/test_invariants.py`
  - `tests/test_mcp_api.py`
  - `tests/test_mcp_connections_api.py`
  - `tests/test_mcp_connections_repository.py`
  - `tests/test_mcp_local_development.py`
  - `tests/test_mcp_turn_api.py`
  - `tests/test_memory.py`
  - `tests/test_memory_classifier_prompt.py`
  - `tests/test_memory_error_sanitization.py`
  - `tests/test_message_timestamps.py`
  - `tests/test_persisted_event_error_sanitization.py`
  - `tests/test_runtime_context.py`
  - `tests/test_scheduled_current_day.py`
  - `tests/test_scheduled_report_accuracy.py`
  - `tests/test_scheduled_report_logs.py`
  - `tests/test_scheduled_summary.py`
  - `tests/test_scheduled_summary_updates.py`
  - `tests/test_service.py`
  - `tests/test_task_api.py`
  - `tests/test_task_invariant_validation.py`
  - `tests/test_task_plan_approval.py`
  - `tests/test_task_report_retry.py`
  - `tests/test_task_retry.py`
  - `tests/test_test_storage_isolation.py`
  - `tests/test_user_profile_rework.py`
  - `tests/test_user_profiles.py`
  - `tests/test_session_memory_coordinator.py`
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `PENDING`

## Justification

- Reason Category: `REFACTORING_NO_BEHAVIOR_CHANGE`
- Why The Test Changed: Import paths and monkeypatch targets must point to the canonical implementation after deletion of compatibility modules.
- Old Expected Behavior: The same repository, model, classifier, API, and failure scenarios are validated through compatibility imports.
- New Expected Behavior: The same assertions validate the same behavior through canonical imports and monkeypatch targets.
- Affected Acceptance Criteria: User request to remove all Python modules containing only imports without changing runtime behavior.
- Specification Changed: `NO`
- Incorrect Artifact: `UNCLEAR`

## Deletion Approval

- Existing Test Deleted: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`
- Approval Evidence: No existing test case or assertion will be removed.

## Reviewer Assessment

- Is The Justification Valid: `YES`
- Does The Test Still Protect The Same Behavior: `YES`
- Was Production Code Incorrectly Avoided: `NO`
- Should Production Code Have Been Fixed Instead: `NO`
- Notes: The test diff changes only import paths and three monkeypatch targets; no assertions, test cases, or fixtures were removed. The worktree remains uncommitted for user review.

## Evidence

- Diff Evidence: `git diff -- tests` shows canonical import and monkeypatch path updates; no test case or assertion removal.
- Verification Commands: Baseline `./harness/scripts/test.sh` (275 passed, 1 warning); after-change `PYTHONPATH=src .venv/bin/python -m pytest -q tests -p no:cacheprovider` (275 passed, 1 warning), `./harness/scripts/check.sh`.
- Related Production Changes: Removal of 46 import-only or re-export-only Python modules under `src/copia` and canonical import updates. Public exports in package `__init__.py` remain intact.
