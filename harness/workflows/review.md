# Review Workflow

## Когда использовать

При ревью task plan, implementation diff или завершённой работы agent.

## Назначение

Независимо проверить работу на defects.

## Обязательные входные данные

- Task и acceptance criteria.
- Diff или changed files.
- Verification claims.

## Приоритеты

1. Correctness.
2. Невыполненные requirements.
3. Regressions.
4. Security.
5. Concurrency и lifecycle.
6. Architecture boundaries.
7. Missing tests.
8. Unnecessary complexity.
9. Случайные unrelated changes.

## Процедура

1. Прочитай task, plan и relevant architecture docs.
2. Изучи diff и changed tests.
3. Если изменялись существующие tests, примени `harness/workflows/test-integrity-gate.md`:
   - проверь наличие Test Change Report;
   - ответь на Test Integrity Review questions;
   - вынеси `APPROVED`, `APPROVED_WITH_NOTES` или `REJECTED`;
   - при rejection верни implementation к implementer.
4. Если existing test удалён, проверь explicit human approval до approval работы.
5. Сверь claims с files и command output.
6. Сообщи concrete findings с severity и file references.
7. Включи open questions и residual risk.

## Обязательные проверки

- Как минимум изучи changed tests и связанный production code.
- При изменении existing tests изучи Test Change Report и зафиксируй Test Integrity verdict.

## Запрещённое поведение

- Редактирование files без явного запроса.
- Style-only findings, если они не влияют на maintainability или policy.

## Результат

Используй `harness/templates/review-report.md`. Review должно быть read-only, если edits явно не запрошены.
