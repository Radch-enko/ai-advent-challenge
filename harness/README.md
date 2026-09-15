# Copia AI SDLC Harness

The harness is Copia's repository-local operating system for AI-assisted development. It turns requests into scoped tasks, routes implementation and review, and provides deterministic quality gates.

## Structure

- `workflows/`: feature, bugfix, refactoring, planning, review, infrastructure, task authoring, and test-integrity procedures.
- `policies/`: architecture, coding, testing, security, and Git rules.
- `templates/`: task, plan, ADR, review, completion, and test-integrity artifacts.
- `scripts/`: dependency setup, tests, frontend build, lint, security, architecture, and canonical checks.
- `git-hooks/`: repository-managed pre-commit and pre-push gates.
- `evals/`: smoke scenarios for agent process quality.

## Lifecycle

```text
request -> task context -> plan -> scoped implementation -> focused checks
        -> full check -> diff review -> completion report
```

Use a matching active task when one exists. Otherwise use the explicit user request as task context or author a task first when ambiguity would force implementation guesses.

## Commands

```bash
./harness/scripts/check-dependencies.sh
./harness/scripts/test.sh
./harness/scripts/build-check.sh
./harness/scripts/lint.sh
./harness/scripts/security-check.sh
./harness/scripts/architecture-check.sh
./harness/scripts/check.sh
./utils/install-git-hooks.sh
```

`check.sh` is the canonical gate. Scripts are non-interactive except dependency installation and must fail with a non-zero exit code when a required check fails.
