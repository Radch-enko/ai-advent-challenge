---
description: Запускай Expert Council complexity gate, сохраняй artifacts и запускай full council только при необходимости.
agent: orchestrator
---

Запусти протокол Expert Council для этого decision:

```text
$ARGUMENTS
```

Используй OpenCode subagent council protocol из `.agents/skills/expert-council/SKILL.md`.

Создай run directory в:

```text
docs/reports/expert-council/<timestamp>-<task-slug>/
```

Сначала рассчитай и сохрани `complexity-gate.md`:

```yaml
council_required: true
score: 7
reasons:
  - architectural decision
  - cross-module impact
  - irreversible migration
```

Маршрутизируй по score:

- `score < 3`: single agent; не запускай council.
- `score 3-5`: lightweight review; не запускай council.
- `score >= 6`: full council.

Важно: запускай `visionary`, `skeptic`, `realist` и `council-judge` напрямую из orchestrator только при `score >= 6`.

Всегда создавай `task.md`, `complexity-gate.md` и `verdict.md`. При `score < 6` `verdict.md` должен объяснять, почему
full council не запускался, и какой lighter route следует использовать. При `score >= 6` запусти `visionary`, `skeptic`
и `realist`, сохрани их ответы, проведи один critique round, передай все materials в `council-judge` и запиши
`verdict.md`.

Все experts и judge должны оставаться read-only. Основывай product и business reasoning на user request, `AGENTS.md`,
`README.md` и `docs/product/`, если они есть. Не редактируй application code. Не выполняй commit или push.
