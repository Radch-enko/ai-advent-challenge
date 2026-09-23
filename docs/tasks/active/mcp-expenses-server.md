# Задача

ID: mcp-expenses-server
Status: active
Title: MCP server for expense search and creation

## Цель

Создать отдельное MCP server приложение в `mcp-server`, предоставляющее LLM-neutral tools для поиска и добавления
расходов через Copia FastAPI backend.

## Контекст

Расходы хранятся backend в `~/.copia/files/finances.xlsx`. MCP server не работает с Excel напрямую и использует
FastAPI как единственную integration boundary.

## Функциональные требования

- `search_expenses` поддерживает inclusive RFC 3339 `occurred_from`/`occurred_to`, category, name, merchant,
  payment_method, tags, inclusive min/max amount, общий text query, page_size и cursor.
- Category и payment method сравниваются case-insensitive exact; name, merchant и общий text — case-insensitive
  substring; запись должна содержать все указанные tags по case-insensitive exact match.
- Общий text ищет по name, category, merchant, payment method, note и tags.
- `add_expense` принимает полный `ExpenseCreate` contract и возвращает созданный расход.
- FastAPI `GET /expenses` поддерживает тот же search contract до pagination.
- MCP tools возвращают typed structured output и ожидаемые failures как MCP `ToolError`.

## Нефункциональные требования

- Использовать официальный Python MCP SDK и stdio transport.
- `mcp-server` имеет собственные `pyproject.toml`, README и `copia-finances-mcp` entrypoint.
- Backend URL берётся из `COPIA_API_URL`, default `http://127.0.0.1:8000`.
- HTTP timeout конечный; network errors и malformed responses не раскрывают URL, traceback или response dump.

## Вне области задачи

- Streamable HTTP/SSE transport, authentication, LLM-specific prompts, resources и sampling.
- Прямой Excel access из MCP server.
- Редактирование/удаление, totals, analytics, concurrency control и snapshot pagination.

## Acceptance criteria

- [ ] Официальный MCP client выполняет handshake и видит ровно `search_expenses` и `add_expense`.
- [ ] Search tool передаёт полный набор filters и возвращает structured paginated result.
- [ ] Add tool передаёт полный expense payload и возвращает structured expense.
- [ ] Backend применяет согласованные filters до pagination и отклоняет invalid ranges.
- [ ] Backend/network/response failures преобразуются в bounded MCP tool errors.
- [ ] Focused tests, architecture/security checks и project gate выполнены либо limitation зафиксирован.

## Связанные файлы и модули

- `mcp-server`
- `src/copia/domain/services`
- `src/copia/api/service.py`
- `tests`

## Ограничения

- Python 3.11+, `mcp>=2,<3`, `httpx>=0.27,<1`.
- Search cursor используется только вместе с тем же набором filters.
- Existing tests не изменяются и не удаляются.

## Проверка

- Focused backend tests.
- Focused `mcp-server` tests.
- `./harness/scripts/lint.sh`, `architecture-check.sh`, `security-check.sh`.
- `./harness/scripts/check.sh`.

## Риски

- Offset cursor не обеспечивает snapshot consistency при изменении расходов между запросами.
- MCP tools недоступны, если FastAPI backend не запущен.

## Открытые вопросы

Нет.
