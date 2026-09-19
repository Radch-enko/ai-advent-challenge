# Task Authoring Workflow

## Когда использовать

При преобразовании неформального request в полную task specification в `docs/tasks/active/` или `docs/tasks/backlog/`.

## Назначение

Создать task specification с ограниченной областью и проверяемыми требованиями без изменения production code.

## Обязательные входные данные

- Informal request.
- `AGENTS.md`.
- Repository assessment и relevant product/architecture docs.
- `harness/templates/task.md`.

## Процедура

1. Определи goal и context.
2. Изучи actual repository modules, связанные с request.
3. Зафиксируй assumptions.
4. Опиши functional и non-functional requirements.
5. Определи out-of-scope behavior.
6. Напиши testable acceptance criteria.
7. Определи relevant modules и files.
8. До перечисления проверь существование verification commands.
9. Перечисли risks и open questions.
10. Сохрани task file в requested task directory.

## Обязательные проверки

- Проверь существование commands до того, как перечислять их как required verification.

## Запрещённое поведение

- Молчаливое расширение ambiguous scope.
- Выдумывание modules или tools.
- Изменение production code.

## Результат

Task file по шаблону `harness/templates/task.md`.
