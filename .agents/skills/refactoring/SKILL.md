---
name: refactoring
description: Используй при изменении структуры Copia с сохранением поведения через явные invariants и verification.
---

# Refactoring

Используй `harness/workflows/refactoring.md` как нормативный workflow.

Определи invariants, зафиксируй before-change evidence, если это практически возможно, внеси минимальное structural
change, применяй `harness/workflows/test-integrity-gate.md` при изменении tests, выполни equivalent after-change
verification и `./harness/scripts/check.sh`, затем сообщи invariant evidence и rollback notes.

Не вноси user-visible behavior changes, не пересекай module boundaries без approval, не скрывай failures и не выполняй
commit/push без явного запроса.
