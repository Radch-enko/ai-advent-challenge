---
description: Create a scoped Copia task spec from an informal request without modifying production code.
agent: orchestrator
---

Route this task-authoring request through the Copia orchestrator.

Request:

```text
$ARGUMENTS
```

Have `architect` identify scope and relevant repository facts, then have `implementer` use the `task-authoring` skill and `harness/workflows/task-authoring.md`. Save the result under `docs/tasks/active/` unless the request explicitly says backlog. Do not modify production code. Do not commit or push.
