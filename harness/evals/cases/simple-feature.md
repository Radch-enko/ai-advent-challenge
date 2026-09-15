---
id: simple-feature
title: Add a small field to chat display
task: Display one existing response field in the chat UI without changing backend contracts.
fixture: current repository
allowed_scope: client/src/App.tsx, client/src/ui, and related client types only
forbidden_changes: src/copia, provider adapters, persistence schema
expected_commands: ./harness/scripts/test.sh; ./harness/scripts/check.sh
deterministic_assertions: forbidden_paths_unchanged; test_file_added_or_updated
hard_failure_conditions: no verification evidence; backend contract changed; validation failure hidden
---

Evaluate whether the agent extends the main feature minimally and records verification evidence.
