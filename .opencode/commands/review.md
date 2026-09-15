---
description: Review the current Copia diff or task output without editing files.
agent: orchestrator
---

Route this review request through the Copia orchestrator.

Review target:

```text
$ARGUMENTS
```

Delegate read-only review to `reviewer`. Follow `harness/workflows/review.md` and use `harness/templates/review-report.md`. Read the active task, plan when present, current diff, tests, and verification claims. Do not edit files. Report findings first, ordered by severity, with file references. Do not commit or push.
