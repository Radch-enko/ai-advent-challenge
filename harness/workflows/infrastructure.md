# Infrastructure Workflow

## Purpose

Use this workflow for CI/CD, validation job quality, repository automation, local hooks, build tooling, and operational scripts.

This workflow is not for ordinary product features, UI changes, domain logic, or server endpoints unless the task changes how those areas are built, checked, released, deployed, or automated.

## Entry Criteria

Use this workflow when the task includes one or more of:

- CI workflow files, CI runners, job ordering, caching, artifacts, notifications, or required checks.
- Harness scripts, evals, Git hooks, validation gates, or automation quality.
- Build, packaging, deployment, release, or local developer automation.
- Tool configuration, dependency setup, or release and deployment automation.
- Secret-handling, environment variable, or runtime configuration changes for infrastructure.

If the task only needs validation results, use the tester workflow instead. If the task only needs a review, use `harness/workflows/review.md`.

## Required Inputs

- Task context or explicit user request.
- Affected infrastructure surface:
  - CI/CD and jobs.
  - Harness scripts and gates.
  - Git hooks or evals.
  - Deployment or operational automation.
- Expected quality signal: faster checks, stricter checks, clearer failures, safer automation, or documented operational behavior.
- Acceptance criteria mapped to executable commands or explicit manual verification.

## Procedure

1. Read `AGENTS.md` and any nested `AGENTS.md` files in affected directories.
2. Check `docs/tasks/active/` and adopt only a clearly matching task.
3. Read relevant policies in `harness/policies/`, especially `security.md`, `testing.md`, and `git.md`.
4. Inspect the affected scripts, workflows, configuration, and documentation before editing.
5. Identify whether the change affects developer-local checks, CI-only checks, packaging, or deployment.
6. Keep the change isolated from product modules unless the task explicitly changes build validation for those modules.
7. Preserve secret safety:
   - Do not commit secrets or local runtime config.
   - Use placeholders in examples.
   - Avoid printing secret values in scripts or logs.
8. Keep scripts non-interactive and fail with non-zero exit codes on required failures.
9. Add or update focused tests, eval cases, or script validation when practical.
10. Run the narrowest relevant command first, then `./harness/scripts/check.sh` when feasible.
11. Review `git status --short`, `git diff --stat`, and `git diff`.
12. Report evidence, assumptions, unresolved risks, and any checks that could not be run.

## Verification Guidance

Prefer deterministic verification in this order:

- For harness eval metadata: `./harness/evals/run-evals.sh`.
- For validation scripts: run the changed script directly.
- For build tooling: run the narrowest affected Python or frontend command.
- For repository-wide impact: `./harness/scripts/check.sh`.
- For CI-only behavior that cannot run locally: validate syntax where possible and report the manual or CI-only gap.

## Out Of Scope

- Product feature implementation unless infrastructure work requires a minimal supporting change.
- Broad CI/CD redesign without explicit acceptance criteria.
- Adding third-party hosted services or new dependencies without task justification.
- Creating, reading, or exposing secrets.
- Replacing existing gates with weaker checks.

## Completion Requirements

The completion report must include:

- Infrastructure surface changed.
- Quality or automation behavior added or preserved.
- Commands run and exact results.
- Secret-handling assumptions.
- CI-only or host-only residual risk.
- Whether `Infrastructurer` was required by context and why.
