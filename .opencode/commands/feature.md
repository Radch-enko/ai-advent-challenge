---
description: Реализуй существующую Copia feature task specification через feature skill и harness workflow.
agent: orchestrator
---

Route marker: `FEATURE_SPEC_ONLY`

Это strict specification-driven implementation route. Он никогда не должен запускать Expert Council или Expert Council
complexity gate.

Input contract:

- `$ARGUMENTS` должен содержать ровно один repository-relative path.
- Path должен указывать на существующую Markdown task specification в `docs/tasks/active/` или `docs/tasks/backlog/`.
- Не принимай inline task text, natural-language implementation request или inferred/arbitrary task file вместо path.
- Если argument отсутствует, содержит более одного path, находится вне allowed directories, не заканчивается на `.md`
  или не существует, остановись и верни actionable error без делегирования работы.

Task specification path:

```text
$ARGUMENTS
```

После проверки и чтения specification используй её как единственный task context. Попроси `architect` подтвердить
feature workflow и verification plan, `implementer` внести минимальное scoped change, `tester` проверить его, а
`reviewer` проверить final diff. При actionable issues от tester или reviewer вернись к `implementer` для rework. Не
выполняй commit или push без явного запроса.
