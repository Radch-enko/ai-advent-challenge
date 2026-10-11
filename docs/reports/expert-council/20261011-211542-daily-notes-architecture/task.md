# Expert Council Task

## Decision

Оценить архитектурное решение Copia для ежедневных заметок: агент Ollama вызывает MCP tool с правками, каждый вызов подтверждается пользователем; MCP server проксирует в FastAPI backend; backend ведёт Markdown-файл по строгому шаблону в специальной папке базы знаний.

## Scope

- Учесть существующий finances MCP proxy.
- Учесть read-only bind mount базы знаний в `compose.yaml`.
- Учесть ручную индексацию документов.
- Оценить безопасность путей и конкурентные правки.
- Не изменять production code.
- Не читать личные данные.

## Sources

- User-provided decision text.
- `AGENTS.md`.
- `README.md`.
- `docs/product/vision.md`.
- `compose.yaml`.
- `mcp-server/README.md`.

## Protocol

Full Expert Council v3: independent Visionary, Skeptic and Realist perspectives, one critique round, then Council Judge. Все participants read-only; artifacts этого run — единственные допустимые записи.
