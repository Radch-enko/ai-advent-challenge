---
name: bugfix
description: Use when fixing broken Copia behavior or failing checks through the bugfix workflow.
---

# Bugfix

Use `harness/workflows/bugfix.md` as the authoritative workflow.

Reproduce or document inability to reproduce, isolate root cause, add regression coverage where practical, make the minimal fix, apply `harness/workflows/test-integrity-gate.md` when tests change, run focused checks plus `./harness/scripts/check.sh` when feasible, and report root cause, fix, evidence, and residual risk.

Do not suppress failures, weaken checks, change existing tests without Test Integrity Gate justification, broaden scope into refactoring, or commit/push unless explicitly requested.
