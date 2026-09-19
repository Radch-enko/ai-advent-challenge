---
description: Запускай каноническую Copia validation и сообщай точные результаты команд без изменений production code.
agent: orchestrator
---

Направь этот validation request через Copia orchestrator.

Scope или notes:

```text
$ARGUMENTS
```

Делегируй validation к `tester`. Запусти `./harness/scripts/check.sh`, если пользователь не сузил scope. Сообщи точные
commands, results, failures, вероятные причины и residual risk. Не изменяй production code. Не выполняй commit или push.
