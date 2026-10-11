# Realist Perspective

## Feasibility Verdict

Решение условно реализуемо с одной обязательной коррекцией: не писать в read-only bind mount. Минимальный вариант — writable `/data/documents/daily-notes/` на существующем named volume рядом с read-only `CopiaKnowledgeBase`, если это соответствует требованию «специальная папка базы знаний».

## Boundary and MVP Contract

Добавить отдельный daily-notes domain/application/data/api модуль, thin MCP tool и тесты; не менять `McpToolLoop` и existing finances proxy pattern. Backend принимает typed fields, сам вычисляет `YYYY-MM-DD.md`, рендерит strict template и не принимает arbitrary path.

MVP должен включать containment validation, atomic temp-file + `os.replace`/fsync, single-process per-note locking, bounded body and deterministic/idempotent semantics. Manual reindex остаётся текущим контрактом и должен быть явно отражён в UX.

## Sequencing and Verification

Сначала domain/repository tests, затем application/API, затем MCP proxy и approval smoke. Проверить traversal, absolute paths, symlink, concurrent calls, duplicate/retry, strict template, proxy delegation, manual reindex and architecture/security checks.

## Read-only Resolution

Option A — писать в writable named-volume subdirectory under `/data/documents` — сохраняет canonical `CopiaKnowledgeBase` read-only и не требует compose change. Если требование означает именно host `CopiaKnowledgeBase`, потребуется отдельный writable bind mount, что является отдельным архитектурным решением и расширяет риск.

## Migration and Risks

Данных для миграции нет; rollback удаляет route/tool, оставляя созданные Markdown. До реализации нужна task spec с точным шаблоном, create/append semantics, date source и целевой папкой. Single-process lock не покрывает будущие multi-worker deployments; это нужно зафиксировать или заменить file lock.
