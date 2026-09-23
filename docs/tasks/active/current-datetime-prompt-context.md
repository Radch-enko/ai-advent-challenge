# Задача

ID: current-datetime-prompt-context
Status: completed
Title: Current date and time in agent system context

## Цель

Передавать модели актуальные локальные дату, время и timezone при каждом пользовательском turn, чтобы ответы агентов
не зависели от устаревшего знания модели о текущем времени.

## Контекст

Сейчас system prompt содержит роль агента и контекст памяти, но не содержит runtime-время backend. Значение должно
формироваться заново для каждого основного LLM-вызова и работать одинаково для обычного chat, MCP-enabled chat и Task
mode.

## Функциональные требования

- Перед каждым основным agent LLM call формировать runtime-блок с локальным RFC 3339 datetime, timezone label и UTC
  offset backend-процесса.
- Добавлять блок в system message, не изменяя persisted `AgentConfig`, transcript или исходный system prompt.
- Применять блок к обычному synchronous chat, asynchronous MCP turn, retry основного chat turn и всем LLM stages Task
  mode.
- Формировать значение заново для каждого вызова, включая последовательные provider calls внутри MCP tool loop.
- Не добавлять runtime-блок во внутренние summarizer, facts updater, memory classifier и title-generation calls.

## Нефункциональные требования

- Реализация остаётся provider-neutral и не зависит от OpenAI/GigaChat payload format.
- Формат блока детерминирован и покрывается unit tests с явно переданным datetime.
- Существующие persisted messages и конфигурации не мигрируются.

## Вне области задачи

- Выбор timezone пользователем или агентом.
- Синхронизация времени с внешним NTP/API.
- Сохранение runtime-времени в историю сообщений.
- Передача времени внутренним maintenance LLM calls.

## Acceptance criteria

- [x] Обычный agent call получает system context с актуальным local datetime, timezone label и UTC offset.
- [x] Task mode stages получают тот же runtime context.
- [x] Каждый provider call в MCP tool loop получает заново сформированный runtime context.
- [x] Runtime context не сохраняется в `AgentConfig` или transcript.
- [x] Summarizer, facts updater, memory classifier и title generation сохраняют прежний prompt behavior.
- [x] Existing non-MCP и MCP behavior продолжает проходить focused и repository checks.

## Связанные файлы и модули

- `src/copia/domain/services/context_strategy.py`
- `src/copia/domain/models/agent.py`
- `src/copia/domain/services/mcp_tool_loop.py`
- `src/copia/api/service.py`
- `tests`

## Ограничения

- Использовать локальное время backend host.
- Не добавлять dependencies.
- Не менять существующие tests без Test Integrity Gate.

## Проверка

- Новые focused pytest tests для rendering, обычного agent call, MCP loop и Task mode.
- `./harness/scripts/architecture-check.sh`
- `./harness/scripts/check.sh`

## Риски

- Локальная timezone backend может отличаться от timezone пользователя при удалённом deployment; настройка timezone
  остаётся вне текущего scope.

## Открытые вопросы

Нет.
