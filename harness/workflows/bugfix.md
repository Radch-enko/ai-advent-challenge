# Bugfix Workflow

## Когда использовать

Для исправления сломанного, регрессировавшего или неожиданного поведения.

## Назначение

Исправить defect с regression evidence.

## Обязательные входные данные

- Шаги воспроизведения или явное failure evidence.
- Ожидаемое поведение.
- Затронутый module или user path, если известен.

## Сопоставление задачи

Перед использованием любой task из `docs/tasks/active/` сопоставь её goal, scope, affected area и acceptance criteria с
текущим user request.

- Если task явно соответствует request, используй её как authoritative task specification.
- Если task не соответствует request, игнорируй её в текущем run. Не переноси её acceptance criteria, constraints, scope
  или verification commands; используй текущий user request как task context или создай новую task specification через
  `harness/workflows/task-authoring.md`.
- Если соответствие неоднозначно, зафиксируй ambiguity вместо молчаливого принятия task. Если user request достаточно
  подробен, предпочти создать новый task context.

## Процедура

1. Воспроизведи failure или задокументируй, почему его нельзя воспроизвести.
2. Изолируй root cause через минимальный релевантный code path.
3. Если возможно, добавь regression test, который падает до fix.
4. Внеси минимальное corrective change.
5. Примени `harness/workflows/test-integrity-gate.md`, если tests изменялись:
   - новые regression tests разрешены автоматически;
   - изменение существующих tests требует Test Change Report до продолжения review;
   - удаление существующих tests требует явного human approval до продолжения implementation.
6. Проверь связанное behavior на аналогичные regressions.
7. Запусти focused tests для affected area.
8. Запусти `./harness/scripts/check.sh`, если это возможно.
9. Сообщи root cause, fix, evidence и residual risk.

## Обязательные проверки

- Regression test или задокументированная причина, почему он был непрактичен.
- `./harness/scripts/check.sh`, если это возможно.

## Запрещённое поведение

- Broad refactoring, замаскированный под fix.
- Подавление failure вместо его исправления.
- Изменение существующих tests без обоснования по Test Integrity Gate.

## Критерии завершения

Defect исправлен, regression coverage существует или причина его отсутствия задокументирована, unrelated behavior не
изменилось.

## Результат

Сообщи root cause, fix, commands, results и residual risk.
