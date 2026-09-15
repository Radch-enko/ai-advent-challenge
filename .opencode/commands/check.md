---
description: Run canonical Copia validation and report exact command results without production edits.
agent: orchestrator
---

Route this validation request through the Copia orchestrator.

Scope or notes:

```text
$ARGUMENTS
```

Delegate validation to `tester`. Run `./harness/scripts/check.sh` unless the user narrows the scope. Report exact commands, results, failures, likely causes, and residual risk. Do not modify production code. Do not commit or push.
