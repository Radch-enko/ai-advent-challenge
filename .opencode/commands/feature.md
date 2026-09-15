---
description: Implement an active Copia feature task through the feature skill and harness workflow.
agent: orchestrator
---

Route this request through the Copia multi-agent delivery loop.

Task ID or path:

```text
$ARGUMENTS
```

Have `architect` confirm the feature workflow and verification plan, `implementer` make the minimal scoped change, `tester` verify it, and `reviewer` review the final diff. Rework through `implementer` when tester or reviewer reports actionable issues. Do not commit or push unless explicitly requested.
