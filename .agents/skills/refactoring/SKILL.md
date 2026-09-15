---
name: refactoring
description: Use when changing Copia structure while preserving behavior through explicit invariants and verification.
---

# Refactoring

Use `harness/workflows/refactoring.md` as the authoritative workflow.

Define invariants, capture before-change evidence where practical, make the smallest structural change, apply `harness/workflows/test-integrity-gate.md` when tests change, run equivalent after-change verification plus `./harness/scripts/check.sh`, and report invariant evidence with rollback notes.

Do not introduce user-visible behavior changes, cross module boundaries without approval, hide failures, or commit/push unless explicitly requested.
