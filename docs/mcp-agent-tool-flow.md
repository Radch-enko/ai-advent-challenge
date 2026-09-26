# MCP tools в Copia: текущая архитектура и flow

## 1. MCP server

`mcp-server` — отдельное Python-приложение, реализующее стандартный MCP protocol. Оно не работает напрямую с Excel:
для хранения расходов оно обращается к FastAPI backend через HTTP.

Основной код server:

- [mcp-server/server.py](../mcp-server/server.py)
- [mcp-server/README.md](../mcp-server/README.md)

Поддерживаемые transports:

- `stdio` — режим по умолчанию;
- `streamable-http` — локальный endpoint `http://127.0.0.1:8001/mcp`.

Запуск HTTP-режима:

```bash
copia-finances-mcp --transport streamable-http
```

Адрес Copia backend задаётся через `COPIA_API_URL`, по умолчанию:

```text
http://127.0.0.1:8000
```

### MCP tool: `search_expenses`

Вызывает backend `GET /expenses`.

Параметры:

```json
{
  "occurred_from": "2026-01-01T00:00:00+06:00",
  "occurred_to": "2026-01-31T23:59:59+06:00",
  "category": "Продукты",
  "name": "кофе",
  "merchant": "Яндекс",
  "payment_method": "card",
  "tags": ["еда"],
  "min_amount_rub": 100,
  "max_amount_rub": 5000,
  "text": "завтрак",
  "page_size": 20,
  "cursor": null
}
```

Все поля опциональны. Фильтры дат и суммы inclusive. `page_size` принимает значения от `1` до `100`. Ответ:

```json
{
  "items": [
    {
      "id": "uuid",
      "occurred_at": "2026-01-15T12:30:00+06:00",
      "name": "Кофе",
      "category": "Продукты",
      "amount_rub": "250.00",
      "merchant": "Coffee Shop",
      "payment_method": "card",
      "note": null,
      "tags": ["еда"],
      "created_at": "2026-01-15T12:31:00+06:00"
    }
  ],
  "next_cursor": null
}
```

### MCP tool: `add_expense`

Вызывает backend `POST /expenses`.

Обязательные поля:

```json
{
  "occurred_at": "2026-01-15T12:30:00+06:00",
  "name": "Кофе",
  "category": "Продукты",
  "amount_rub": 250.0
}
```

Опциональные поля: `merchant`, `payment_method`, `note`, `tags`. Backend генерирует `id` и `created_at`, после чего
MCP server возвращает полностью сохранённую запись.

## 2. Backend MCP connection API

MCP connections хранятся в `~/.copia/mcp_connections.json`. Persisted connection содержит endpoint, server metadata и
последний список schemas; секретные значения не сохраняются.

Основная реализация:

- [src/copia/service.py](../src/copia/service.py)
- [src/copia/mcp/data/mcp_connections_repository.py](../src/copia/mcp/data/mcp_connections_repository.py)
- [src/copia/mcp/data/mcp_client.py](../src/copia/mcp/data/mcp_client.py)
- [src/copia/mcp/domain/models/mcp_connection.py](../src/copia/mcp/domain/models/mcp_connection.py)

### `GET /mcp/connections`

Возвращает список зарегистрированных connections.

### `POST /mcp/connections`

Создаёт connection и сразу выполняет MCP discovery.

```json
{
  "id": "finances",
  "name": "Copia Finances",
  "endpoint": "http://127.0.0.1:8001/mcp",
  "header_name": null,
  "header_value_env": null
}
```

### `PUT /mcp/connections/{connection_id}`

Обновляет connection. `id` в body должен совпадать с path parameter. После обновления выполняется новый discovery.

### `POST /mcp/connections/{connection_id}/test`

Проверяет endpoint, выполняет MCP initialization и `tools/list`, затем обновляет cached server metadata и schemas.

### `DELETE /mcp/connections/{connection_id}`

Удаляет connection. Если он используется агентом или profile, возвращает `409 Conflict`.

### Безопасность MCP client

Backend вызывает MCP через официальный Streamable HTTP client и сохраняет ограничения:

- timeout;
- SSRF и loopback validation;
- DNS pinning;
- redirect validation;
- ограничение размера ответа;
- redaction credentials и технических деталей ошибок.

Операции MCP client:

- `initialize`;
- `tools/list`;
- `tools/call`.

## 3. End-to-end flow сообщения и tool call

### Шаг 1. Сообщение пользователя

Для MCP-enabled агента frontend вызывает:

```http
POST /sessions/{session_id}/turns
```

```json
{
  "content": "Сколько я потратил на продукты в этом месяце?"
}
```

Backend возвращает `202 Accepted` и `turn_id`:

```json
{
  "id": "turn-id",
  "session_id": "session-id",
  "status": "running",
  "approval": null,
  "result": null,
  "error": null
}
```

Старый endpoint `POST /sessions/{session_id}/messages` сохраняется для агентов без MCP. Для MCP-enabled agent он
возвращает `409` с указанием использовать `/turns`.

### Шаг 2. Turn worker и discovery

Backend запускает worker, блокирует второй активный turn в той же session и отправляет SSE event `turn_started`.

Перед каждым tool-enabled turn backend заново вызывает `initialize` и `tools/list`, затем:

1. выбирает connections из `AgentConfig.mcp_access`;
2. оставляет только явно включённые tools;
3. удаляет исчезнувшие или недоступные tools;
4. формирует стабильные provider aliases длиной до 64 символов.

Контракт allowlist хранится в `AgentConfig`:

```json
{
  "mcp_access": [
    {
      "connection_id": "finances",
      "enabled_tools": ["search_expenses", "add_expense"]
    }
  ]
}
```

Основная domain-реализация:

- [src/copia/mcp/domain/services/mcp_tool_loop.py](../src/copia/mcp/domain/services/mcp_tool_loop.py)
- [src/copia/agents/domain/models/agent_config.py](../src/copia/agents/domain/models/agent_config.py)

### Шаг 3. Вызов LLM с tool schemas

Backend передаёт модели system/user messages и только разрешённые schemas:

- OpenAI получает native `tools`;
- GigaChat получает native `functions`.

Summarizer, memory classifier, facts updater и title generation tool schemas не получают.

Provider adapters:

- [src/copia/providers/data/llm.py](../src/copia/providers/data/llm.py)
- [src/copia/providers/application/llm_router.py](../src/copia/providers/application/llm_router.py)

### Шаг 4. Модель возвращает tool call

Модель может вернуть alias инструмента и JSON arguments:

```json
{
  "name": "mcp_finances_search_expenses_a1b2c3d4e5",
  "arguments": {
    "category": "Продукты",
    "occurred_from": "2026-01-01T00:00:00+06:00",
    "occurred_to": "2026-01-31T23:59:59+06:00"
  }
}
```

Backend проверяет alias, исходный connection/tool и JSON arguments. Автоматического выполнения до подтверждения нет.

### Шаг 5. Approval event

Backend создаёт pending approval и отправляет через:

```http
GET /sessions/{session_id}/turns/{turn_id}/events
```

```text
event: tool_approval_required
```

Payload содержит server, tool и arguments, но не credentials.

Frontend показывает inline card с кнопками «Разрешить» и «Отклонить».

### Шаг 6. Решение пользователя

Frontend вызывает:

```http
POST /sessions/{session_id}/mcp-approvals/{approval_id}
```

Для разрешения:

```json
{"decision": "approve"}
```

Для отказа:

```json
{"decision": "reject"}
```

Повторное решение возвращает `409 Conflict`.

### Шаг 7. MCP `tools/call`

После `approve` backend отправляет SSE event `tool_running`, frontend показывает:

```text
Выполняю search_expenses
```

Затем backend вызывает MCP `tools/call`. MCP server преобразует этот вызов в HTTP-запрос к Copia backend:

```text
MCP client → MCP server → GET/POST /expenses → Excel repository
```

После выполнения отправляется `tool_completed`. Ошибки ограничены и очищены от traceback, credentials и URL dumps.

### Шаг 8. Tool result возвращается модели

Результат MCP добавляется в provider-native tool/function-result message. Затем backend снова вызывает LLM.

Если модель возвращает ещё один tool call, цикл повторяется. Вызовы последовательные, максимум 8 за один turn.

При `reject` MCP не вызывается; модели передаётся synthetic result:

```text
User rejected this tool call
```

### Шаг 9. Финальный ответ

Когда модель возвращает обычный текст без нового tool call, backend:

1. сохраняет assistant message в session transcript;
2. сохраняет bounded audit tool calls;
3. переводит turn в `completed`;
4. отправляет SSE event `final`.

Статус можно получить через:

```http
GET /sessions/{session_id}/turns/{turn_id}
```

События можно восстановить после reconnect через SSE endpoint. Терминальные события — `final` или `error`.

## 4. Основные turn endpoints

| Метод | Endpoint | Назначение |
| --- | --- | --- |
| `POST` | `/sessions/{session_id}/turns` | Запустить MCP-enabled turn, ответ `202` с `turn_id` |
| `GET` | `/sessions/{session_id}/turns/{turn_id}` | Получить текущий status/result/error |
| `GET` | `/sessions/{session_id}/turns/{turn_id}/events` | SSE stream с replay событий turn |
| `POST` | `/sessions/{session_id}/mcp-approvals/{approval_id}` | Approve/reject ожидающий tool call |

Основные SSE events:

- `turn_started`;
- `tool_approval_required`;
- `tool_running`;
- `tool_completed`;
- `final`;
- `error`.
