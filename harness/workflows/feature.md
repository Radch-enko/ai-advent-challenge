# Feature Workflow

## Когда использовать

Для добавления небольшого user-visible behavior или расширения существующего behavior без изменения architecture.

## Назначение

Реализовать небольшую feature через repository SDLC harness.

## Обязательные входные данные

- Явный path к task specification в `docs/tasks/active/` или `docs/tasks/backlog/`, переданный через `/feature`, с
  testable acceptance criteria.
- `AGENTS.md`.
- Relevant product и architecture docs.
- Известные constraints и out-of-scope items.
- Applicable policies в `harness/policies/`.
- `harness/workflows/test-integrity-gate.md` при изменении tests.

## Сопоставление задачи

Перед использованием переданной task specification изучи её goal, scope, affected area и acceptance criteria. Явный
`/feature` path в `docs/tasks/active/` или `docs/tasks/backlog/` является authoritative для этого route; не сопоставляй
его с unrelated или implicit user request.

При вызове через `/feature` command работает только со specification: требуй ровно один существующий Markdown path в
`docs/tasks/active/` или `docs/tasks/backlog/`. Отклоняй missing, ambiguous, outside-directory или nonexistent paths.
Не заменяй specification inline request text или произвольной backlog task. Явный `/feature` route также пропускает
Expert Council complexity gate и сам Expert Council.

- Если explicit path valid, используй этот file как authoritative task specification.
- Если specification неполна или оставляет blocking questions нерешёнными, остановись и сообщи blocker вместо guesses.

## Процедура

1. Установи task context.
2. Прочитай relevant documentation и repository facts.
3. Создай implementation plan.
4. Реализуй минимальное change, удовлетворяющее task.
5. Примени Test Integrity Gate, если tests изменялись:
   - новые tests разрешены автоматически;
   - изменение существующих tests требует Test Change Report до продолжения review;
   - удаление существующих tests требует явного human approval до продолжения implementation.
6. Выполни self-review diff на scope, architecture, tests и hidden failures.
7. Запусти focused checks для affected modules или behavior.
8. Запусти `./harness/scripts/check.sh`, если это возможно.
9. Подготовь completion report.

Порядок этапов:

```text
Task context
-> Relevant documentation and repository facts
-> Implementation planning
-> Implementation
-> Review
-> Verification
```

## Обязательные проверки

- Focused tests для affected code, если доступны.
- `./harness/scripts/check.sh` или точное описание failure и limitation.

## Границы

- Не вводи циклические зависимости между фичами; новую прямую зависимость обоснуй владельцем модели или контракта.
- При integration changes сохраняй согласованность backend/client contracts и provider-agnostic models.
- Не переделывай UI, dependency wiring или package structure, если это не требуется task.
- Не redesign architecture вне task scope.
- Не скрывай failing checks.
- Не изменяй существующие tests без соблюдения `harness/workflows/test-integrity-gate.md`.

## Критерии завершения

Acceptance criteria выполнены, verification evidence зафиксирован, unrelated changes отсутствуют, unresolved risks
описаны.

## Результат

Используй `harness/templates/completion-report.md`.
