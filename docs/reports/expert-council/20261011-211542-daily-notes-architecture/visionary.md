# Visionary Perspective

## Recommendation

Рассматривать Daily Notes как переход Copia к долгосрочной локальной памяти, но сохранить user-in-the-loop. Предпочтительны append-only/idempotent операции, backend-owned шаблон и атомарная запись. Для записи потребуется writable область; безопаснее выделить её отдельно, чем ослаблять read-only canonical bind mount.

## Product Opportunity

Сценарий даёт low-friction journaling, усиливает последующий RAG и соответствует приоритетам Copia: инструменты, локальный контроль данных и настраиваемая автономность.

## Target Operating Model

Ollama формирует структурированные поля; UI показывает preview и получает явное подтверждение; MCP остаётся thin proxy; FastAPI валидирует, форматирует и атомарно пишет в разрешённую папку; индексация сначала остаётся ручной.

## Strategic Trade-offs

Строгий шаблон улучшает поиск и проверяемость, но ограничивает свободное редактирование. Ручная индексация сохраняет текущую простоту и контроль, но создаёт stale-search gap. Синхронная запись проще, event-driven reindex — будущий шаг.

## Non-negotiable Guardrails

- явное подтверждение каждой пользовательской операции;
- backend не принимает произвольный target path от модели;
- containment/path validation, защита от symlink и TOCTOU;
- atomic write, idempotency и concurrency control;
- запись только в специально выделенную writable область.

## Phased Adoption

1. MVP append/create для текущего дня с фиксированным шаблоном.
2. Поддержка секций и устойчивой идемпотентности.
3. Автоматическая или частичная индексация после успешной записи.

## Acceptance Signals

Нет потери или дублирования записей при повторе/конкуренции; запись появляется в разрешённой папке; ручной reindex делает её доступной поиску; все tool calls проходят approval.

## Assumptions and Unknowns

Предполагается, что пользователь примет отдельную writable область. Нужно уточнить физическую целевую папку, create vs append и точный шаблон.
