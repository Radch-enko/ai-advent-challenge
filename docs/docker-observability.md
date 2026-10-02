# Локальный запуск Copia в Docker и просмотр HTTP-трафика

Эта конфигурация предназначена для локальной разработки. Она запускает Vite frontend, FastAPI backend и MCP server. SigNoz устанавливается отдельно и не входит в Compose Copia.

## Требования

- Docker Desktop с работающим Docker Engine и Compose.
- SigNoz self-hosted, доступный с хоста на `http://localhost:8080`; OTLP gRPC endpoint по умолчанию `localhost:4317`.
- Node/Python на хосте не нужны для запуска через Compose.

SigNoz UI: [http://localhost:8080](http://localhost:8080). Для запросов и ответов используйте **Logs → Explorer**; **Live** в List View показывает новые события по мере поступления. Для корреляции входящего запроса, provider HTTP и MCP открывайте связанный trace. Официальная инструкция установки: [Docker install](https://signoz.io/docs/install/docker/), сведения об OTLP: [self-hosted ingestion](https://signoz.io/docs/ingestion/self-hosted/overview/).

## Настройка `.env`

Создайте локальный `.env` в корне репозитория на основе `.env.example`, затем укажите необходимые ключи провайдеров. Не коммитьте `.env` и не копируйте его в Docker image: файл исключён через `.dockerignore`.

Compose передаёт значения из `.env` backend-контейнеру. Для локального SigNoz из контейнера используется `host.docker.internal`. Чтобы указать другой OTLP gRPC endpoint, задайте `OTEL_EXPORTER_OTLP_ENDPOINT`, например:

```dotenv
OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4317
```

В Compose включена отправка traces и structured HTTP logs через OpenTelemetry. В обычном запуске backend без Compose telemetry выключена. Входящие HTTP и завершённые исходящие provider/MCP HTTP-запросы представлены одной записью `http.exchange`: в её JSON body находятся `exchange_id`, `direction`, request и response с URL, headers и телами. JSON-тела передаются как структурированные JSON-объекты, а не JSON-текст в строковом атрибуте. Для OpenAI streaming-запроса в response входят распарсенные SSE data-фреймы и итоговый ответ (текст, tool calls и usage). У входящего `/conversation` и MCP SSE response содержат распарсенные SSE events. Provider-обмены внутри conversation несут `conversation_id` и `request_id` в attributes для фильтрации. Данные персонального характера и переписка не скрываются. Поля с именами вроде `api_key`, `authorization`, `token`, `password`, `secret`, секреты в URL и известные token-паттерны маскируются перед экспортом. Неизвестные форматы секретов могут не распознаться — не помещайте credentials в произвольные поля payload.

Захват ограничен 1 MiB на тело. Если тело больше, оно не экспортируется частично и получает `body_truncated=true`; транспорт приложения продолжает работать без изменений. Binary и некорректный JSON пропускаются, заголовки и остальные метаданные остаются. Для SSE body содержит массив `events`, где поле `data` — JSON-объект, если data-фрейм содержит валидный JSON. Каждая завершённая запись несёт стандартные OTel timestamp/severity/resource/trace поля дополнительно к exchange payload.

Для этой задачи удобнее сохранённое представление Logs Explorer, а не dashboard с агрегированными графиками: view запоминает запрос, фильтры, колонки и layout, а строка лога по-прежнему открывается с полным JSON body. Откройте **Logs → Explorer**, задайте выражение:

```text
service.name = 'copia-backend' AND event.name = 'http.exchange'
```

Оставьте List View, добавьте колонки `conversation_id`, `request_id`, `exchange_id`, `http.direction`, `http.request.method`, `url.full` и `http.response.status_code`. Для поиска одного диалога отфильтруйте attribute `conversation_id`; `request_id` находит конкретную отправку, `exchange_id` идентифицирует одну пару request/response. Открыв запись, разверните её JSON body: request и response находятся рядом, заголовки — map, JSON payload — объект, SSE — массив событий. Внизу Explorer нажмите **Save this view**, назовите его `Copia — HTTP exchanges`. События также связаны trace/span контекстом; для цепочки backend → provider/MCP можно открыть связанный trace. См. [официальное руководство SigNoz по Logs Explorer](https://signoz.io/docs/userguide/logs_query_builder/) и [FAQ о сохранённых views](https://signoz.io/docs/logs-management/troubleshooting/faqs/).

Отключите `COPIA_OTEL_CAPTURE_HTTP_BODIES`, чтобы оставить URL, статус и безопасные headers без тел; HTTP-логи и traces при этом продолжают собираться. SigNoz хранит дополнительную копию тел запросов и ответов: ограничьте доступ к панели и настройте срок хранения/удаление в своём отдельном SigNoz deployment.

## Запуск всех сервисов

Из корня репозитория:

```bash
docker compose up --build
```

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend API: [http://localhost:8000](http://localhost:8000)
- MCP server: внутренний адрес `http://mcp-server:8001/mcp`, не опубликован на хосте.
- SigNoz: [http://localhost:8080](http://localhost:8080) — запускается отдельно.

Frontend отправляет `/api/...` в Vite proxy, а тот пересылает запросы на backend. Backend может обращаться к MCP по внутреннему DNS имени. Браузеру прямой доступ к MCP не требуется.

Полезные команды:

```bash
docker compose logs -f backend
docker compose logs -f frontend mcp-server
docker compose down
```

`docker compose down` сохраняет named volume `copia-data`. Чтобы удалить Copia data, используйте `docker compose down -v` осознанно: это необратимо удалит локальные данные приложения. Данные SigNoz хранятся в его собственном Compose stack и управляются отдельно.

### Пути профилей и постоянных данных

Файл встроенных профилей находится в образе по пути `/app/profiles.json`; Compose явно передаёт этот путь backend через `COPIA_PROFILES_PATH`. Профили не хранятся в volume и не изменяются самим приложением. После изменения локального `profiles.json` пересоберите backend: `docker compose up -d --build backend`.

Все изменяемые данные Copia находятся под `/data`, который подключён к named volume `copia-data`. Поэтому обычное пересоздание контейнера их сохраняет:

| Путь в контейнере | Данные |
| --- | --- |
| `/data/sessions` | Сессии, логи агентов, рабочая и ожидающая подтверждения память |
| `/data/memory` | Долгосрочная память профилей |
| `/data/artifacts/<session-id>` | Изображения PNG, созданные MCP-инструментами |
| `/data/files/finances.xlsx` | Книга расходов |
| `/data/invariants.json` | Инварианты |
| `/data/user_profiles.json` | Пользовательские профили общения |
| `/data/mcp_connections.json` | Настройки MCP-подключений |
| `/data/scheduled-runs`, `/data/schedules.json`, `/data/scheduler-state.json` | История запусков и состояние расписания |

В Docker эти файлы не записываются в host `~/.copia`: данные принадлежат Docker volume. Команда `docker compose down` volume сохраняет, а `docker compose down -v` удаляет его вместе с данными.

## Раздельный запуск

Собрать всё можно один раз командой `docker compose build`. Затем запускайте нужные сервисы:

```bash
docker compose up --build backend
docker compose up --build mcp-server
docker compose up --build frontend
```

При раздельном запуске frontend всё равно нуждается в backend; backend — в MCP для вызовов MCP-инструментов. Compose автоматически запустит зависимости. Без Docker сохраняется существующий host workflow из корневого README (`./scripts/restart-dev.sh`); OpenTelemetry там выключена по умолчанию.

## Диагностика

- Если SigNoz недоступен, проверьте, что его OTLP gRPC порт опубликован на хосте как `4317` и задан верный `OTEL_EXPORTER_OTLP_ENDPOINT`.
- В SigNoz ищите service `copia-backend`. Данные экспортируются пакетами, поэтому между HTTP запросом и появлением записи возможна небольшая задержка; это не гарантированная синхронная доставка.
- MCP доступен только backend-контейнеру и разрешён для точного адреса `http://mcp-server:8001/mcp`. Это не отключает SSRF-защиту пользовательских MCP endpoints.
- Если backend не стартует, посмотрите `docker compose logs backend`; проверьте переменные в локальном `.env`, не публикуя их.
