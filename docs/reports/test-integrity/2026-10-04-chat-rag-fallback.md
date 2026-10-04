# Отчёт Test Integrity

## Резюме

- Task: Обновить fallback обычного RAG-чата и восстановить поиск по исходному вопросу при промахе query rewrite.
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: `tests/test_rag_sessions.py`, `tests/test_document_retriever.py`
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `PENDING`

## Обоснование

- Reason Category: `SPECIFICATION_CHANGED`
- Why The Test Changed: Пользователь уточнил, что формулировка об отсутствии релевантной информации должна быть ответом LLM, а не добавляться приложением. Добавлен regression case для включённого по умолчанию query rewrite: если переписанный запрос не проходит порог similarity, retriever повторяет поиск по исходному вопросу.
- Old Expected Behavior: Приложение добавляло фиксированную фразу к ответу без проверенных цитат. Query rewrite сразу заменял исходный запрос, и пустой результат завершал поиск без попытки по исходной формулировке.
- New Expected Behavior: Приложение сохраняет текст ответа LLM без дописывания фразы. При пустом результате rewritten query выполняется один fallback search по исходному вопросу; подтверждённые цитаты и источники по-прежнему проверяются обычным способом.
- Affected Acceptance Criteria: Ответ без источников сообщает об их отсутствии формулировкой LLM; RAG находит доступный чанк по исходному запросу после промаха rewrite; неподтверждённые источники не сохраняются.
- Specification Changed: `YES`
- Incorrect Artifact: `PRODUCTION_CODE`

## Согласование удаления

- Existing Test Deleted: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`
- Approval Evidence: Существующие сценарии сохранены; изменены ожидаемые ответы согласно уточнённому контракту. Для поиска добавлен отдельный regression case.

## Оценка ревьюера

- Is The Justification Valid: `YES`
- Does The Test Still Protect The Same Behavior: `YES`
- Was Production Code Incorrectly Avoided: `NO`
- Should Production Code Have Been Fixed Instead: `YES`
- Synthetic Test Data Review: `YES`
- Synthetic Test Data Evidence: Тесты используют вымышленные демонстрационные данные: арифметический ответ, `blue kite` и фиктивный чанк о переезде.
- Notes: Для структурированного no-evidence ответа приложение больше не переписывает `answer`. Если LLM вернёт невалидный structured response, приложение извлечёт доступный текст ответа без добавления фиксированной фразы; соблюдение формулировки в таком случае зависит от модели.

## Evidence

- Diff Evidence: `tests/test_rag_sessions.py` проверяет, что no-evidence fallback сохраняет формулировку LLM; `tests/test_document_retriever.py` проверяет повторный поиск исходного вопроса при пустом результате rewritten query.
- Verification Commands: `pytest tests/test_document_retriever.py tests/test_rag_sessions.py -p no:cacheprovider` — 12 passed; `./harness/scripts/lint.sh` — passed; `./harness/scripts/type-check.sh` — passed; `./harness/scripts/security-check.sh` — passed; `./harness/scripts/architecture-check.sh` — passed; `git diff --check` — passed. `./harness/scripts/check.sh` built the client and passed 7 client tests, then reported 3 failures in unrelated MCP/observability tests and 350 passed backend tests. Пользователь отдельно выполняет длинные ручные диалоги.
- Related Production Changes: `src/copia/document_indexing/application/document_retriever.py`, `src/copia/document_indexing/application/rag_citations.py`, `src/copia/document_indexing/prompts/rag_chat_context.md`, `src/copia/document_indexing/prompts/rag_no_evidence.md`.
