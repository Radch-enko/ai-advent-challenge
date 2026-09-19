---
name: expert-council
description: Используй для оценки нетривиальных product, business, architecture, planning или trade-off решений Copia через OpenCode subagent Expert Council v3.
---

# Expert Council

Используй этот skill для запуска протокола OpenCode subagent Expert Council v3 при planning, design, architecture,
review или trade-off decisions.

## Complexity gate

Council не должен запускаться для каждой задачи. Перед запуском экспертов council рассчитай и зафиксируй:

```yaml
council_required: true
score: 7
reasons:
  - architectural decision
  - cross-module impact
  - irreversible migration
```

Используй следующую шкалу оценки:

| Критерий | Баллы |
| --- | ---: |
| Изменение public API | 2 |
| Архитектурная миграция | 2 |
| Влияние на security/privacy | 3 |
| Несколько равнозначных решений | 2 |
| Затронуто более трёх модулей | 1 |
| Необратимое решение | 2 |
| Высокая неопределённость | 2 |

Пороги маршрутизации:

- `score < 3`: используй одного агента; council не запускай.
- `score 3-5`: используй lightweight review; council не запускай.
- `score >= 6`: запускай полный council.

Важное правило: полный Expert Council можно запускать только при `score >= 6`.

## Оркестрация council в OpenCode

Стандартный `orchestrator` должен рассчитывать complexity gate для каждого пользовательского запроса, кроме
`FEATURE_SPEC_ONLY`, до обычной маршрутизации. Strict route `FEATURE_SPEC_ONLY` из `.opencode/commands/feature.md` —
явное исключение: он должен проверить переданную спецификацию задачи, а затем пропустить gate и весь протокол Expert
Council.

При `score >= 6` `orchestrator` должен напрямую запустить полный Expert Council, вызвав `visionary`, `skeptic`,
`realist` и `council-judge`.

Не направляй requests с `score >= 6` к `architect`, `reviewer`, `general` или в обычный delivery loop до появления
вердикта council.

Orchestrator должен:

- создать `docs/reports/expert-council/<timestamp>-<task-slug>/task.md`;
- рассчитать и сохранить результат complexity gate до запуска экспертов;
- запускать `visionary`, `skeptic` и `realist` только при `score >= 6`;
- сохранять ответы экспертов только при `score >= 6`;
- проводить один critique round только при `score >= 6`;
- передавать все материалы в `council-judge` только при `score >= 6`;
- создать `docs/reports/expert-council/<timestamp>-<task-slug>/verdict.md`.

Эксперты:

- `visionary`: use `openrouter/google/gemini-3-flash-preview`.
- `skeptic`: use `openrouter/deepseek/deepseek-v4-flash`.
- `realist`: use `openrouter/z-ai/glm-5.2`.

Все эксперты и judge должны оставаться read-only. Orchestrator может редактировать только council artifacts в
`docs/reports/expert-council/**`.

## Product и business context

- Перед подготовкой perspectives изучи релевантные product и business documents в `docs/product/`.
- Предпочитай читать все files в `docs/product/`, если решение затрагивает roadmap, scope, users, positioning,
  prioritization, monetization или MVP trade-offs.
- Основывай perspectives, disagreements, critique и final decision на найденной там product/business information.
- Если в `docs/product/` нет релевантной информации, явно укажи это в report и продолжи с лучшими доступными sources.
- Не выдумывай product или business facts, которые не подтверждены user request или `docs/product/`.

## Протокол

1. Рассчитай score complexity gate.
   - Не рассчитывай gate для `FEATURE_SPEC_ONLY`; проверь task path и продолжи напрямую в feature delivery loop.
   - При `score < 3` используй single-agent handling и не запускай экспертов council.
   - При `score 3-5` используй lightweight review и не запускай экспертов council.
   - При `score >= 6` продолжи с полным council.
2. Создай report directory при `score >= 6` или когда пользователь явно вызывает `/expert-council`.
3. Сохрани результат complexity gate в `complexity-gate.md` и кратко изложи его в `task.md`.
4. Собери product и business context из `docs/product/`.
5. Подготовь три независимые expert perspectives через `visionary`, `skeptic` и `realist`.
6. Сохрани ответы экспертов.
7. Перечисли disagreements.
8. Проведи один critique round.
9. Передай все материалы в `council-judge`.
10. Подготовь `verdict.md`.

## Формат отчёта

Для запусков full council сохраняй результат как набор Markdown-артефактов в:

```text
docs/reports/expert-council/<timestamp>-<task-slug>/
```

Используй task slug из 4–5 слов в lowercase через hyphen, например:

```text
20260727-153012-navigation-state-policy/
```

Обязательные files для каждого явного запуска `/expert-council` и каждого full council run:

- `task.md`
- `complexity-gate.md`
- `verdict.md`

Обязательные files для full council run с `score >= 6`:

- `visionary.md`
- `skeptic.md`
- `realist.md`
- `critique.md`
- `judge.md`

`verdict.md` должен включать:

- `## Complexity Gate`
- `## Decision`
- `## Why This Wins`
- `## Rejected Alternatives`
- `## Product/Business Basis`
- `## Acceptance Criteria`
- `## Follow-up Checks`
- `## Assumptions`
- `## Known Risks`
- `## Confidence`
