---
description: Создавай Copia task spec с ограниченной областью из неформального request без изменения production code.
agent: orchestrator
---

Направь этот task-authoring request через Copia orchestrator.

Request:

```text
$ARGUMENTS
```

Попроси `architect` определить scope и релевантные repository facts, затем попроси `implementer` использовать
`task-authoring` skill и `harness/workflows/task-authoring.md`. Сохрани result в `docs/tasks/active/`, если request явно
не указывает backlog. Не изменяй production code. Не выполняй commit или push.
