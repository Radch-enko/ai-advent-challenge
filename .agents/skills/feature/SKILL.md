---
name: feature
description: Use when implementing a new Copia feature from an active repository task through the feature workflow.
---

# Feature

Use `harness/workflows/feature.md` as the authoritative workflow.

Load `AGENTS.md`, confirm any task under `docs/tasks/active/` matches the current user request before treating it as authoritative, then load relevant architecture docs and policies in `harness/policies/`. Map acceptance criteria to verification, implement minimally, apply `harness/workflows/test-integrity-gate.md` when tests change, run focused checks plus `./harness/scripts/check.sh` when feasible, review the diff, and report using `harness/templates/completion-report.md`.

Do not redesign architecture, hide failing checks, create feature-to-feature dependencies, or commit/push unless explicitly requested.
