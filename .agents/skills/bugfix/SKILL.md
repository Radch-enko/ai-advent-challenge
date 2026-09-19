---
name: bugfix
description: Используй при исправлении сломанного поведения Copia или неуспешных проверок по bugfix workflow.
---

# Bugfix

Используй `harness/workflows/bugfix.md` как нормативный workflow.

Воспроизведи проблему или зафиксируй невозможность воспроизведения, изолируй корневую причину, добавь regression
coverage, когда это практически возможно, внеси минимальное исправление, применяй
`harness/workflows/test-integrity-gate.md` при изменении tests, запускай focused checks и `./harness/scripts/check.sh`,
если это возможно, и сообщай корневую причину, исправление, evidence и остаточный риск.

Не подавляй failures, не ослабляй checks, не изменяй существующие tests без обоснования по Test Integrity Gate, не
расширяй scope до refactoring и не выполняй commit/push без явного запроса.
