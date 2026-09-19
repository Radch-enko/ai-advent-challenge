---
description: Выполняй behavior-preserving refactoring Copia с явными invariants и verification.
agent: orchestrator
---

Направь этот request через Copia multi-agent delivery loop.

Refactoring task или scope:

```text
$ARGUMENTS
```

Попроси `architect` определить invariants и refactoring scope, `implementer` внести минимальное behavior-preserving
change, `tester` проверить invariants/checks, а `reviewer` проверить финальный diff. При actionable issues от tester или
reviewer вернись к `implementer` для rework. Не выполняй commit или push без явного запроса.
