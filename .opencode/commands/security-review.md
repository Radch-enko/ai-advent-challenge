---
description: Run a focused read-only Copia security review.
agent: orchestrator
---

Route this security review request through the Copia orchestrator.

Security review target:

```text
$ARGUMENTS
```

Delegate read-only review to `security-reviewer`. Use `harness/policies/security.md` as the primary policy source, inspect the active task when relevant, inspect the current diff and related files, run `./harness/scripts/security-check.sh` when allowed, and report findings first. Do not edit files. Do not inspect or print real secrets. Do not commit or push.
