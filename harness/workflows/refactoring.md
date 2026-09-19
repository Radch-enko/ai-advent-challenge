# Refactoring Workflow

## Когда использовать

При изменении структуры с сохранением behavior.

## Назначение

Улучшить structure с сохранением behavior.

## Обязательные входные данные

- Behavioral invariants.
- Scope и affected modules.
- Rollback plan.

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

1. Определи behavior, который должен остаться неизменным.
2. Зафиксируй before-change verification evidence.
3. Спланируй минимальное structural change.
4. Избегай opportunistic feature work.
5. Реализуй change небольшими шагами.
6. Примени `harness/workflows/test-integrity-gate.md`, если tests изменялись:
   - новые tests разрешены автоматически;
   - изменение существующих tests требует Test Change Report до продолжения review;
   - удаление существующих tests требует явного human approval до продолжения implementation.
7. По возможности выполни одинаковые focused checks до и после.
8. Запусти `./harness/scripts/check.sh`.
9. Сообщи before-and-after evidence.

## Обязательные проверки

- Before-and-after focused verification, где это практически возможно.
- `./harness/scripts/check.sh`.

## Запрещённое поведение

- Opportunistic user-visible changes.
- Изменение module boundaries без явного approval.
- Изменение существующих tests без обоснования по Test Integrity Gate.

## Критерии завершения

Behavior доказуемо не изменилось, scope остался ограниченным, rollback понятен.

## Результат

Сообщи changed structure, invariant evidence, commands и rollback notes.
