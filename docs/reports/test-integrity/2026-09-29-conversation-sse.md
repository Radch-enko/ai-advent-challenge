# Отчёт Test Integrity

## Резюме

- Task: Перенести MCP execution и approval state под conversations, добавить durable bounded SSE replay и восстановление client stream после reload.
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: legacy session/agent message, raw completion, and summarization retry cases in `tests/test_day11_latest_review_blockers.py`, `tests/test_provider_error_safety.py`, `tests/test_day12_final_reviewer_regressions.py`, `tests/test_persisted_event_error_sanitization.py`, `tests/test_memory_error_sanitization.py`, `tests/test_execution_summary.py`, `tests/test_day11_facts_redaction_and_context_race.py`, `tests/test_invariants.py`, `tests/test_service.py`, `tests/test_user_profile_rework.py`, `tests/test_memory.py`, `tests/test_day11_long_term_memory_toggle_race.py`, `tests/test_day11_session_message_concurrency.py`, `tests/test_mcp_turn_api.py`, `tests/test_task_api.py`, `tests/test_user_profiles.py`, `tests/test_day11_retry_message_concurrency.py`; new coverage in `tests/test_conversation_api.py`, `tests/test_provider_streaming.py`, `client/tests/conversation.test.ts`, `client/tests/conversation-recovery.test.ts`
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `MERGED`

## Обоснование

- Reason Category: `ACCEPTANCE_CRITERIA_CHANGED`
- Why The Test Changed: MCP turn-local runtime and session flags are removed; test coverage moves to the owning `ConversationRun`, and restart recovery is asserted through persisted event replay.
- Old Expected Behavior: MCP execution state and approvals live in `McpTurnRuntime`; interrupted turns are marked on session load through `mcp_turn_*` fields.
- New Expected Behavior: MCP approval wait/decision state is part of `ConversationRun`; SQLite restores saved events and converts an unfinished run into `conversation.failed` with `interrupted_by_restart`.
- Affected Acceptance Criteria: `AC1` MCP state is conversation-owned; `AC2` no old turn routes/runtime names remain; `AC3` replay survives store recreation and restart; `AC4` storage is bounded; `AC5` client reconnect survives reload.
- Specification Changed: `YES`
- Incorrect Artifact: `TEST`

## Согласование удаления

- Existing Test Deleted: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`
- Approval Evidence: Пользователь явно запросил удаление старых routes и реализацию нового механизма; существующие тестовые проверки должны быть переписаны, а не удалены.

## Оценка ревьюера

- Is The Justification Valid: `YES`.
- Does The Test Still Protect The Same Behavior: `YES`.
- Was Production Code Incorrectly Avoided: `NO`.
- Should Production Code Have Been Fixed Instead: `NO`.
- Notes: Existing MCP tests retain assertions for approval, tool execution ordering, and task approval behavior while moving session execution coverage to `ConversationRun`. Restart and retention tests use temporary SQLite databases. The new browser recovery test covers reload replay and terminal cleanup. No existing test file or assertion was removed without replacement.

## Evidence

- Diff Evidence: `tests/test_mcp_turn_api.py` transfers MCP approval and event-order assertions from the deleted turn runtime to `ConversationRun`; session message/agent/completion/retry tests now assert `/conversation` behavior; restart, quota, replay, and browser reload assertions cover the new contract.
- Verification Commands: `./harness/scripts/check.sh` — passed (288 pytest tests, 4 Vitest tests, TypeScript, Vite build, Ruff, ESLint, Prettier, Gitleaks, and architecture check); `./harness/scripts/security-check.sh` — passed (no leaks).
- Related Production Changes: `src/copia/conversations/**`, `src/copia/mcp/**`, `src/copia/sessions/**`, `src/copia/service.py`, `client/src/**`.
