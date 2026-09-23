# Задача

ID: local-mcp-http
Status: active
Title: Local Streamable HTTP for the expenses MCP server

## Цель

Разрешить тестирование expenses MCP server через экран MCP в локальном Copia frontend.

## Контекст

FastAPI работает на `127.0.0.1:8000`, а expenses MCP server по умолчанию использует stdio. Copia discovery намеренно
принимает только public HTTPS endpoints и блокирует loopback для защиты от SSRF.

## Функциональные требования

- `copia-finances-mcp --transport streamable-http` запускает стандартный MCP Streamable HTTP endpoint на
  `http://127.0.0.1:8001/mcp`.
- Запуск без аргументов сохраняет stdio transport.
- Copia discovery по умолчанию принимает HTTP/HTTPS endpoints только на exact loopback host `localhost` или loopback
  IP literals; `COPIA_ALLOW_LOCAL_MCP=false` явно отключает это поведение.
- Private, link-local, metadata, wildcard и non-loopback addresses остаются запрещены при любом режиме.

## Нефункциональные требования

- Loopback resolution должна быть DNS-rebinding safe: каждый resolved address обязан быть loopback.
- Redirects, proxy environment и response limits остаются неизменными.
- Не добавлять authentication или новые dependencies.

## Вне области задачи

- Remote HTTP hosting, TLS termination, configurable bind address/port/path и production deployment.
- Ослабление защиты для private network endpoints.

## Acceptance criteria

- [ ] CLI выбирает stdio по умолчанию и Streamable HTTP только по explicit flag.
- [ ] HTTP mode использует `127.0.0.1:8001/mcp`.
- [ ] Copia обнаруживает loopback endpoint по умолчанию и отключает его при exact `false`.
- [ ] Public HTTPS behavior и network protections не регрессируют.
- [ ] Focused tests и repository verification выполнены либо limitation зафиксирован.

## Связанные файлы и модули

- `mcp-server/server.py`
- `src/copia/data/mcp_client.py`
- `src/copia/api/service.py`
- `tests`

## Ограничения

- Python 3.11+, официальный MCP SDK.
- Environment override: `COPIA_ALLOW_LOCAL_MCP=false` отключает local MCP discovery.

## Проверка

- Focused MCP CLI и endpoint validation tests.
- MCP discovery integration test.
- `./harness/scripts/check.sh`.

## Риски

- Локальный MCP endpoint не имеет authentication и доступен процессам на том же host.

## Открытые вопросы

Нет.
