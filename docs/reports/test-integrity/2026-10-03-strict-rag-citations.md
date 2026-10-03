# Отчёт Test Integrity

## Резюме

- Task: Строгий RAG с проверяемыми цитатами, безопасным ответом при повторной ошибке цитирования и состоянием «Нужно уточнение» в Task Mode.
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: `tests/test_rag_sessions.py`, `tests/test_task_rag.py`, `tests/test_rag_citations.py`, `tests/test_task_rag_clarification.py`.
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `PENDING`

## Обоснование

- Reason Category: `SPECIFICATION_CHANGED`
- Why The Test Changed: Пользователь изменил ожидаемое поведение после неудачной повторной проверки цитаты: Copia должна показать последнюю читаемую формулировку модели с явной пометкой о непроверенных цитатах вместо технической ошибки.
- Old Expected Behavior: После одной повторной генерации с невалидной цитатой API возвращал `502 rag_citation_validation_failed`, а неподтверждённый ответ не сохранялся.
- New Expected Behavior: После повторной невалидной цитаты Copia показывает последнюю читаемую формулировку модели с заметным предупреждением. Источниками остаются только чанки, чьи `chunk_id` и точные цитаты можно подтвердить; если таких нет, ответ показывается без источников. Ошибки провайдера и индекса по-прежнему остаются ошибками. Task Mode сохраняет предупреждение в видимом плане, сообщениях шагов и отчёте.
- Affected Acceptance Criteria: Ответ после повтора с предупреждением; отсутствие неподтверждённых источников; сохранение предупреждения в истории и Task Mode; прежние проверки валидных цитат и остановки Task Mode при пустом контексте.
- Specification Changed: `YES`
- Incorrect Artifact: `UNCLEAR`

## Согласование удаления

- Existing Test Deleted: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`
- Approval Evidence: Изменяется только синтетический ответ fake provider под новым user-approved response contract; существующие retrieval, persistence и task-stage assertions сохраняются.

## Оценка ревьюера

- Is The Justification Valid: `YES`
- Does The Test Still Protect The Same Behavior: `YES` — checks still cover retrieval, retry count, source selection, persistence, and Task Mode stages; the superseded terminal-error assertion now verifies the approved warning response.
- Was Production Code Incorrectly Avoided: `NO`
- Should Production Code Have Been Fixed Instead: `NO` — old expectations intentionally allowed unverified text and had to change with the approved contract.
- Synthetic Test Data Review: `YES`
- Synthetic Test Data Evidence: Все вопросы, документы, цитаты и ответы в этих тестах являются вымышленными демонстрационными данными.
- Notes: The answer text is shown only after one retry and carries an explicit warning. Source metadata is still selected from retrieved chunks, and quotes are retained only when they exactly occur in those chunks. The repository gate has three unrelated existing failures in MCP request fakes and observability header casing.

## Evidence

- Diff Evidence: `tests/test_rag_sessions.py` checks below-threshold retrieval returns «Не знаю», then verifies a readable answer is persisted with a warning after two invalid citation attempts. `tests/test_rag_citations.py` checks fallback extraction and verified source filtering. `tests/test_task_rag.py` checks the warning appears in the plan, step messages, and report after repeated invalid citations. No existing test case was deleted.
- Verification Commands: Focused RAG/session/Task Mode suite — 35 passed; `./harness/scripts/check.sh` — client typecheck, 7 client tests, and Vite build passed; Python suite: 349 passed, 3 unrelated failures (`tests/test_mcp_client.py` two parameterizations use a request fake without `.method`; `tests/test_observability.py` expects case-sensitive `Authorization` header). `./harness/scripts/lint.sh` — passed; `./harness/scripts/architecture-check.sh` — passed; `./harness/scripts/security-check.sh` — passed; `git diff --check` — passed.
- Related Production Changes: `src/copia/document_indexing/**`, `src/copia/sessions/**`, `src/copia/tasks/**`, `client/src/**`.
