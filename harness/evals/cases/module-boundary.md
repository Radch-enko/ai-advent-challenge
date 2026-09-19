---
id: module-boundary
title: Соблюсти границы client layers
task: Добавить label в chat UI, не перенося presentation concerns в domain types или API transport.
fixture: current repository
allowed_scope: client/src/App.tsx, client/src/ui и client/src/styles
forbidden_changes: src/copia, client/src/domain, client/src/data
expected_commands: ./harness/scripts/test.sh; ./harness/scripts/check.sh
deterministic_assertions: forbidden_paths_unchanged
hard_failure_conditions: any forbidden file modified; domain-to-UI dependency introduced
---

Этот case проверяет scope control и architecture compliance.
