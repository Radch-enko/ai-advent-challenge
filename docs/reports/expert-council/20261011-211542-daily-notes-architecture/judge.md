# Council Judge

Итог: **Approve with conditions** как architecture decision для constrained MVP, но не как готовую production implementation.

Ключевые условия: не писать в текущий read-only `/data/documents/CopiaKnowledgeBase`; до кода создать approved task spec; зафиксировать storage contract, strict template, create/append semantics, idempotency, concurrency, proxy trust и manual reindex UX.

Option A — writable named-volume subdirectory под `/data/documents` — допустим только если «специальная папка базы знаний» означает индексируемое дерево `documents_path`, а не конкретный host-путь `CopiaKnowledgeBase`.

Решение соответствует product-направлению Copia: tools, local data control, user-in-the-loop и configurable autonomy. Неприемлемы запись в read-only mount, arbitrary path от LLM, неатомарный read-modify-write, implicit proxy trust и approval bypass. MVP должен ограничиться одной атомарной операцией на MCP call; ручная индексация остаётся явным контрактом.

Главные follow-ups: уточнить физическую папку; написать task spec; проверить реальные boundaries; выбрать proxy authentication; определить single-process/file-lock strategy; покрыть unit/API/MCP/security/atomicity/retry/concurrency/stale-index tests; проверить, не захватывает ли observability содержимое заметок без необходимости.

Confidence: средняя-высокая; направление подтверждено источниками, но storage target, template и operational semantics не определены.
