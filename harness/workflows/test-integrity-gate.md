# Test Integrity Gate

## Назначение

Делай каждое изменение существующего test явным, доступным для review и основанным на evidence. Gate не запрещает
изменять tests; он отделяет обоснованные corrections specification/test от изменений, скрывающих production defects.

## Уровни риска

| Change | Risk | Gate action |
| --- | --- | --- |
| Создать новый test file или добавить новый test case без ослабления existing assertions | Low | Разрешено автоматически. Test Change Report не требуется. |
| Изменить existing test file | Medium | Остановить implementation flow и создать Test Change Report до продолжения review. |
| Удалить existing test file или убрать existing test case/assertion без замены | High | Остановить implementation flow, объяснить requested deletion и запросить explicit human approval. Без approval implementation остаётся blocked. |

Disabling, ignoring, commenting out, narrowing или weakening existing test считается изменением или удалением test
coverage, которое он ранее предоставлял.

## Определение existing tests

Используй task base revision, branch base или pre-change worktree snapshot как reference point.

- Test path, присутствующий в reference и изменённый в diff, — это existing test modification.
- Test path, присутствующий в reference и отсутствующий после change, — это existing test deletion.
- Newly added test path имеет low risk, если одновременно не заменяет, не отключает и не удаляет existing coverage.

Когда доступна Git metadata, изучай diff такими commands:

```bash
git diff --name-status
git diff -- 'tests/**' 'client/src/**/*.test.ts' 'client/src/**/*.test.tsx'
```

## Обязательное обоснование

Для каждого medium-risk existing test modification создай Test Change Report в:

```text
docs/reports/test-integrity/
```

Используй `harness/templates/test-integrity-report.md`. Report должен включать:

- changed test files;
- risk level;
- controlled reason category;
- why the test changed;
- old expected behavior;
- new expected behavior;
- affected acceptance criteria;
- whether the specification changed;
- whether production code or the test was incorrect;
- reviewer verdict;
- final outcome.

Allowed reason categories:

- `SPECIFICATION_CHANGED`
- `ACCEPTANCE_CRITERIA_CHANGED`
- `TEST_BUG`
- `FLAKY_TEST`
- `IMPLEMENTATION_DETAIL_TO_BEHAVIOR`
- `EXPANDED_COVERAGE`
- `REFACTORING_NO_BEHAVIOR_CHANGE`

Не используй "because the test failed" как justification. Failing test — это evidence для investigation, а не причина
изменять test.

## Связь с acceptance criteria

Если acceptance criteria имеют stable identifiers, укажи их в report. Если нет, используй ближайший task checkbox,
requirement text или `not individually tracked` с кратким описанием. Сохраняй field shape, чтобы будущие AC identifiers
можно было добавить без redesign report.

## Human approval для deletions

Если existing test удалён или existing coverage удалено без замены:

1. Останови implementation.
2. Зафиксируй file, test name если известен, защищённое old behavior, причину requested deletion и рассмотренные safer
   alternatives.
3. Запроси explicit approval у человека.
4. Продолжай только после записи approval в Test Change Report.

## Review Gate

Если existing tests изменялись, review должен явно ответить:

- Is the justification valid?
- Does the test still protect the same behavior?
- Was production code incorrectly avoided?
- Should production code have been fixed instead?

Reviewer verdict должен быть одним из:

- `APPROVED`
- `APPROVED_WITH_NOTES`
- `REJECTED`

Если verdict — `REJECTED`, implementation возвращается к implementer до completion.
