---
description: Исправляй defect Copia с reproduction evidence, regression coverage и full verification.
agent: orchestrator
---

Направь этот request через Copia multi-agent delivery loop.

Bugfix task, failure или path:

```text
$ARGUMENTS
```

Попроси `architect` подтвердить bugfix workflow и verification plan, `implementer` внести минимальное исправление,
`tester` проверить его, а `reviewer` проверить финальный diff. При actionable issues от tester или reviewer вернись к
`implementer` для rework. Не выполняй commit или push без явного запроса.
