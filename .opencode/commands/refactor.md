---
description: Execute behavior-preserving Copia refactoring with explicit invariants and verification.
agent: orchestrator
---

Route this request through the Copia multi-agent delivery loop.

Refactoring task or scope:

```text
$ARGUMENTS
```

Have `architect` define invariants and refactoring scope, `implementer` make the smallest behavior-preserving change, `tester` verify the invariants/checks, and `reviewer` review the final diff. Rework through `implementer` when tester or reviewer reports actionable issues. Do not commit or push unless explicitly requested.
