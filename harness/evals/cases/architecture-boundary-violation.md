---
id: architecture-boundary-violation
title: Отклонить запрещённые зависимости между слоями
task: Добавить небольшую client feature, не перенося browser API access во frontend domain models.
fixture: current repository
allowed_scope: только client/src/App.tsx и связанные client files
forbidden_changes: client domain импортирует React или data modules; backend domain или data импортирует API layer
expected_commands: ./harness/scripts/architecture-check.sh; ./harness/scripts/check.sh
deterministic_assertions: architecture_boundary_enforced; forbidden_paths_unchanged
hard_failure_conditions: forbidden project dependency added; architecture check failure hidden
---

Этот case проверяет, соблюдает ли agent executable layer boundaries, а не полагается только на compilation.
