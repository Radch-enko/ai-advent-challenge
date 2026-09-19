---
description: Запускай focused read-only security review Copia.
agent: orchestrator
---

Направь этот security review request через Copia orchestrator.

Security review target:

```text
$ARGUMENTS
```

Делегируй read-only review к `security-reviewer`. Используй `harness/policies/security.md` как primary policy source,
изучи active task при необходимости, current diff и связанные files, запусти
`./harness/scripts/security-check.sh`, если это разрешено, и сначала сообщи findings. Не редактируй files. Не
просматривай и не выводи реальные secrets. Не выполняй commit или push.
