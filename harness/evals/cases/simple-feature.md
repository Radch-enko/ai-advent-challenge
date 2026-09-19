---
id: simple-feature
title: Добавить небольшое поле в chat display
task: Показать одно существующее response field в chat UI без изменения backend contracts.
fixture: current repository
allowed_scope: только client/src/App.tsx, client/src/ui и связанные client types
forbidden_changes: src/copia, provider adapters, persistence schema
expected_commands: ./harness/scripts/test.sh; ./harness/scripts/check.sh
deterministic_assertions: forbidden_paths_unchanged; test_file_added_or_updated
hard_failure_conditions: no verification evidence; backend contract changed; validation failure hidden
---

Проверь, расширяет ли agent main feature минимально и фиксирует ли verification evidence.
