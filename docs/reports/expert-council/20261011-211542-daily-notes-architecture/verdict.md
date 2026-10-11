# Expert Council Verdict

## Complexity Gate

`council_required: true`, score `7`.

Причины: architectural decision, cross-module impact, irreversible migration. Full Expert Council проведён корректно.

## Decision

**Approve with conditions** как архитектурное решение для constrained MVP, но **не как готовую production implementation**.

Не выполнять запись в текущий read-only bind mount `/data/documents/CopiaKnowledgeBase`. До написания кода требуется approved task spec с точным storage contract.

Option A — writable named-volume subdirectory под `/data/documents` — допустим только если «специальная папка базы знаний» означает индексируемое дерево `documents_path`, а не конкретный host-путь `CopiaKnowledgeBase`. Иначе требуется отдельное решение о writable bind mount.

## Why This Wins

- Соответствует product-направлению Copia: tools, local data control, user-in-the-loop и configurable autonomy.
- Сохраняет явное подтверждение MCP action.
- Оставляет MCP thin proxy, а валидацию, шаблонизацию и запись — backend responsibility.
- Позволяет начать с одной атомарной create/append операции.
- Сохраняет manual indexing как текущий контракт без расширения scope до event-driven reindex.
- Не требует небезопасных допущений о произвольных путях, неатомарной записи или implicit proxy trust.

## Rejected Alternatives

- Запись в `/data/documents/CopiaKnowledgeBase`: отклонено из-за `read_only: true` в `compose.yaml`.
- Приём target path от LLM/MCP client: отклонено из-за traversal, symlink и TOCTOU рисков.
- Прямой read-modify-write без atomic replace и concurrency semantics: отклонено.
- Ослабление per-call approval или accept-all для серии подшагов: отклонено.
- Auto-indexing в MVP: не принято; stale-index risk должен быть отражён в UX.
- Запись именно в host `CopiaKnowledgeBase` без writable-mount решения: отклонено до уточнения.
- Свободное форматирование Markdown моделью: backend-owned strict template.

## Product/Business Basis

Copia — персональный AI assistant для личных productivity-сценариев. Product vision фиксирует local data control, configurable autonomy и MCP actions с approval. README описывает Markdown search и manual reindex. `compose.yaml` подтверждает read-only knowledge-base bind mount и writable named volume `copia-data`. `mcp-server/README.md` подтверждает делегирование в FastAPI через `COPIA_API_URL`.

Quantitative goals, roadmap priority и требование немедленной доступности заметок в product docs не зафиксированы. Поэтому решение ограничено MVP.

## Acceptance Criteria

- Task spec определяет target directory, strict Markdown template, create/append, date/timezone, retry/idempotency, version conflicts, manual reindex UX и deployment concurrency.
- Запись не использует read-only mount; backend сам вычисляет имя файла и не принимает arbitrary path.
- Есть canonical containment validation и защита от traversal, absolute paths, symlink и TOCTOU.
- Запись использует temporary file, fsync и atomic replace.
- Есть per-note concurrency control; single-process invariant явно зафиксирован либо применён межпроцессный lock.
- Retry не создаёт дубликат и не теряет уже записанное.
- Один MCP call — одна атомарная операция, проходящая явное approval.
- Proxy защищён allowlist и согласованным authentication/shared-secret механизмом либо явно документированным локальным threat model.
- Пользователь видит, что manual reindex всё ещё нужен для поиска.
- Покрыты unit, API, MCP approval, security, atomicity, retry, concurrency и manual-indexing проверки.

## Follow-up Checks

1. Уточнить, означает ли «специальная папка базы знаний» `documents_path` или именно host `CopiaKnowledgeBase`.
2. Создать approved task spec до production code.
3. Проверить фактические backend/MCP boundaries; assertions экспертов о внутренних endpoints не считать подтверждёнными до проверки.
4. Выбрать proxy trust mechanism.
5. Проверить single-process deployment; при multi-worker выбрать межпроцессную блокировку.
6. Добавить stale-index acceptance test.
7. Проверить privacy impact OpenTelemetry HTTP body capture из `compose.yaml`.

## Assumptions

- Пользователь согласен на backend-owned strict template.
- MVP допускает manual reindex.
- Одна атомарная create/append операция достаточна.
- Начальный MVP может быть single-process.
- Выделенная writable область сохраняет нужную семантику базы знаний.
- Proxy authentication ещё не выбран.

## Known Risks

Read-only mount остаётся blocker до уточнения storage contract; ошибки path/symlink/TOCTOU могут привести к записи вне разрешённого дерева; неопределённая concurrency semantics может терять заметки; manual indexing создаёт stale-search gap; per-call approval может вызвать fatigue; недостаточная proxy authentication допускает нежелательные calls; single-process lock не масштабируется автоматически; misunderstanding target folder может потребовать writable bind mount; local storage не означает local processing у выбранного AI provider.

## Confidence

**Средняя-высокая.** Направление подтверждено repository и product evidence, но target directory, template, approval granularity, proxy trust и deployment concurrency требуют явной task specification.
