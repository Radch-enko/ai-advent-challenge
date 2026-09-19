---
id: bugfix-with-regression-test
title: Исправить обработку пустого chat message
task: Отклонить blank chat message на подходящей boundary и покрыть behavior regression test, если это практически возможно.
fixture: current repository
allowed_scope: только affected Copia source и связанные tests
forbidden_changes: provider selection, session persistence format, unrelated client redesign
expected_commands: ./harness/scripts/test.sh; ./harness/scripts/check.sh
deterministic_assertions: regression_test_or_rationale
hard_failure_conditions: production-only fix with no test rationale; unrelated UI redesign
---

Agent должен воспроизвести defect или рассуждать на основе его evidence, изолировать state path и избегать broad changes.
