# Test Change Report: feature-owned root migration

- Task: move remaining root `api`, `domain`, and `data` components to their owning capabilities.
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: 57 existing Python test files; see exact list below.
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `PASSED`

## Justification

- Reason Category: `REFACTORING_NO_BEHAVIOR_CHANGE`
- Why The Test Changed: imports and monkeypatch targets must reference the defining modules after relocation; import-only compatibility files are prohibited.
- Old Expected Behavior: all existing assertions and test scenarios pass using the old module paths.
- New Expected Behavior: the same assertions and scenarios pass using canonical feature paths.
- Affected Acceptance Criteria: behavior, HTTP contract, route order, and model identity remain unchanged; root layers contain only application composition and package markers.
- Specification Changed: `NO`
- Incorrect Artifact: `BOTH` (production layout and tests coupled to historical paths).

## Coverage

- Existing Test Deleted: `NO`
- Existing Assertion Removed or Weakened: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`

## Review

- Is The Justification Valid: `YES`
- Does The Test Still Protect The Same Behavior: `YES`
- Was Production Code Incorrectly Avoided: `NO`
- Should Production Code Have Been Fixed Instead: `NO`

## Evidence

- Baseline: `./harness/scripts/check.sh` passed with 277 tests before this migration.
- Baseline OpenAPI and route order: captured in an isolated temporary JSON snapshot before file movement; both equal after migration.
- After-change commands: `./harness/scripts/check.sh` passed with 278 tests, Ruff, TypeScript, frontend build, ESLint, Prettier, Gitleaks, and architecture check; `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_mcp_client.py -p no:cacheprovider` passed 20 tests.
- Test changes: canonical imports and monkeypatch paths only, plus one new assertion-preserving MCP response-size regression. No existing assertions or cases were removed.
- Notes: the repository had pre-existing uncommitted test changes from earlier feature migrations; this report covers the current root migration imports and its added regression.

## Exact existing test paths

- `tests/test_agent.py`
- `tests/test_agent_log_final_reviewer_regressions.py`
- `tests/test_agent_log_persistence.py`
- `tests/test_agent_log_profile_name_sanitization.py`
- `tests/test_agent_log_reviewer_regressions.py`
- `tests/test_agent_log_url_redaction.py`
- `tests/test_agent_logs.py`
- `tests/test_credential_only_logging.py`
- `tests/test_credential_sanitization.py`
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
- `tests/test_mcp_client.py`
- `tests/test_mcp_connections_api.py`
- `tests/test_mcp_connections_repository.py`
- `tests/test_mcp_local_development.py`
- `tests/test_mcp_tool_loop.py`
- `tests/test_mcp_turn_api.py`
- `tests/test_memory.py`
- `tests/test_memory_classifier_prompt.py`
- `tests/test_memory_error_sanitization.py`
- `tests/test_message_timestamps.py`
- `tests/test_model_catalog.py`
- `tests/test_persisted_event_error_sanitization.py`
- `tests/test_provider_tool_calls.py`
- `tests/test_providers.py`
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
- `tests/test_task_state_machine.py`
- `tests/test_test_storage_isolation.py`
- `tests/test_user_profile_rework.py`
- `tests/test_user_profiles.py`
