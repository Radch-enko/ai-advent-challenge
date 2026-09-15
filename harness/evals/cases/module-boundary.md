---
id: module-boundary
title: Respect client layer boundaries
task: Add a label to the chat UI without moving presentation concerns into domain types or API transport.
fixture: current repository
allowed_scope: client/src/App.tsx, client/src/ui, and client/src/styles
forbidden_changes: src/copia, client/src/domain, client/src/data
expected_commands: ./harness/scripts/test.sh; ./harness/scripts/check.sh
deterministic_assertions: forbidden_paths_unchanged
hard_failure_conditions: any forbidden file modified; domain-to-UI dependency introduced
---

This case checks scope control and architecture compliance.
