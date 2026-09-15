---
name: security-review
description: Use when reviewing Copia work that touches secrets, auth/authz, network access, logging, user data, dependencies, CI, deployment, bots, or repository security gates.
---

# Security Review

Use this skill for focused read-only security review.

Read:

- `AGENTS.md`
- `harness/policies/security.md`
- `harness/policies/testing.md`
- `harness/policies/git.md`
- Current task or review target
- Current `git status --short`, `git diff --stat`, and `git diff`
- Changed files and related security-sensitive code paths

Check:

- No secrets, tokens, credentials, signing material, or local config are committed.
- Secrets are not printed in logs, command lines, generated artifacts, examples, or error paths.
- Auth/authz boundaries match the task and fail closed.
- Network access and dependency additions have explicit task justification.
- Inputs, deserialization, storage, telemetry, and logging do not expose sensitive user data.
- CI/deploy scripts avoid dumping environments, artifacts, or tool output that may contain secrets.
- `./harness/scripts/security-check.sh` was run when repository content changed or an exact reason was given.

Stay read-only. Do not inspect real local secrets, keychains, environment values, CI secret values, or untracked secret files.

Report findings first, ordered by severity, with concrete file references. If no findings exist, say so and state residual risk.
