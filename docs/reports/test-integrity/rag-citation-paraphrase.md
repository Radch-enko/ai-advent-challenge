# Отчёт Test Integrity

## Резюме

- Task: Обновить проверку RAG-цитат: сохранять точную проверку выдержки в чанке, разрешить ответу пересказывать источник и не заменять ответ безконтекстным fallback после ошибки цитирования.
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: `tests/test_rag_citations.py`, `tests/test_rag_diagnostics.py`, `tests/test_rag_sessions.py`
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `PENDING`

## Обоснование

- Reason Category: `SPECIFICATION_CHANGED`
- Why The Test Changed: Пользователь выбрал новую ожидаемую политику: проверять точную выдержку по найденному чанку, не требовать буквального включения выдержки в текст ответа и сохранять ответ с предупреждением после неудачной повторной проверки.
- Old Expected Behavior: Цитата считалась недействительной, если её точный текст отсутствовал в `answer`; после двух неудачных проверок session route вызывал LLM ещё раз без найденного RAG-контекста.
- New Expected Behavior: Цитата действительна, если chunk ID принадлежит переданному контексту и точная выдержка присутствует в тексте этого чанка. Ответ может пересказывать источник. После двух неудачных проверок сохраняется последний ответ с предупреждением; дополнительный вызов без найденного контекста не выполняется.
- Affected Acceptance Criteria: Сохранить provenance цитаты; не блокировать естественный пересказ; не терять retrieval context при невалидной цитате; явно предупреждать о непроверенной цитате.
- Specification Changed: `YES`
- Incorrect Artifact: `PRODUCTION_CODE`

## Согласование удаления

- Existing Test Deleted: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`
- Approval Evidence: Явный выбор пользователя в текущем диалоге.

## Оценка ревьюера

- Is The Justification Valid: Да; изменение покрывает выбранную пользователем спецификацию.
- Does The Test Still Protect The Same Behavior: Да; exact chunk ID и точное совпадение выдержки с исходным чанком остаются проверяемыми. Изменён только контракт между выдержкой и формулировкой ответа.
- Was Production Code Incorrectly Avoided: Нет; production validation и RAG fallback будут исправлены.
- Should Production Code Have Been Fixed Instead: Да; изменяемое поведение находится в production validation/fallback, тесты обновляются только для нового контракта.
- Synthetic Test Data Review: `YES`
- Synthetic Test Data Evidence: Используются только вымышленные значения `blue kite`, `fictional-handbook.md`, `handbook-4` и fictional compass fixtures.
- Notes: Existing test expectations are updated to reflect the explicit behavior change; no unrelated assertions are removed. Full check still reports three unrelated failures in MCP transport and observability tests.

## Evidence

- Diff Evidence: Добавлены assertions для paraphrased answer, сохранения предупреждённого ответа после citation failure и отсутствия третьего no-context completion.
- Verification Commands: `.venv/bin/python -m pytest -q tests/test_rag_citations.py tests/test_rag_diagnostics.py tests/test_rag_sessions.py tests/test_execution_summary.py -p no:cacheprovider` — 33 passed; `./harness/scripts/architecture-check.sh` — passed; `./harness/scripts/check.sh` — failed on three unrelated existing failures in `tests/test_mcp_client.py` (two cases) and `tests/test_observability.py`.
- Related Production Changes: `src/copia/document_indexing/application/rag_citations.py`, `src/copia/sessions/api/message_routes.py`, RAG prompt resources.
