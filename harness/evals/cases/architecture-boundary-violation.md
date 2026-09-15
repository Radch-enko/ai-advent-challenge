---
id: architecture-boundary-violation
title: Reject forbidden layer dependencies
task: Add a small client feature without moving browser API access into frontend domain models.
fixture: current repository
allowed_scope: client/src/App.tsx and related client files only
forbidden_changes: client domain importing React or data modules; backend domain or data importing the API layer
expected_commands: ./harness/scripts/architecture-check.sh; ./harness/scripts/check.sh
deterministic_assertions: architecture_boundary_enforced; forbidden_paths_unchanged
hard_failure_conditions: forbidden project dependency added; architecture check failure hidden
---

This case checks whether the agent respects executable layer boundaries rather than relying only on compilation.
