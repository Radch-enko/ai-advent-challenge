---
description: Выполняй ревью текущего Copia diff или task output без редактирования files.
agent: orchestrator
---

Направь этот review request через Copia orchestrator.

Review target:

```text
$ARGUMENTS
```

Делегируй read-only review к `reviewer`. Следуй `harness/workflows/review.md` и используй
`harness/templates/review-report.md`. Прочитай active task, plan при наличии, current diff, tests и verification claims.
Не редактируй files. Сначала сообщай findings, упорядоченные по severity, с file references. Не выполняй commit или
push.
