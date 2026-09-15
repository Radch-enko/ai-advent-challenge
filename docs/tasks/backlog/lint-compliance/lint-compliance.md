# LINT-001 — Make Existing Code Comply With The Strict Lint Gate

## Status

Backlog

## Goal

Make the existing Python and React/TypeScript code pass the repository's configured Ruff, ESLint, and Prettier checks without changing runtime behavior.

## Context

The AI SDLC migration intentionally enables the strict lint gate before reformatting or refactoring product code. Until this task is completed, `./harness/scripts/lint.sh` and the canonical check may fail on pre-existing code.

Migration baseline:

- Ruff lint: 14 findings, including import ordering, two unused imports, quoted annotations, and `StrEnum` modernization.
- Ruff format: 11 files require formatting.
- ESLint: 12 errors and 1 warning in `client/src/App.tsx`, primarily React effect/state and purity findings.
- Prettier: 5 client files require formatting.

## Functional Requirements

- Apply Ruff lint fixes and Ruff formatting to `src` and `tests`.
- Apply ESLint fixes and Prettier formatting to `client/src`.
- Resolve remaining findings manually without weakening or suppressing configured rules.
- Preserve all runtime APIs, persisted data shapes, provider behavior, and UI behavior.

## Non-Functional Requirements

- Keep changes mechanical and reviewable.
- Do not add dependencies or change lint configuration unless a concrete false positive is demonstrated and approved.
- Separate behavior fixes discovered during linting into their own tasks.

## Out Of Scope

- Feature work, architecture redesign, dependency upgrades, and warning cleanup in third-party libraries.
- Changes to provider contracts, session persistence, prompts, or client UX.

## Acceptance Criteria

- [ ] `./harness/scripts/lint.sh` passes.
- [ ] `./harness/scripts/test.sh` reports all 28 baseline tests passing.
- [ ] `./harness/scripts/build-check.sh` passes TypeScript typecheck and Vite production build.
- [ ] `./harness/scripts/architecture-check.sh` passes.
- [ ] Existing test edits have a Test Change Report using reason `REFACTORING_NO_BEHAVIOR_CHANGE`.
- [ ] The final diff contains no lint-rule suppressions or unrelated behavior changes.

## Definition Of Ready

- [x] Scope is limited to existing Python and React/TypeScript source and tests.
- [x] Blocking questions are resolved.
- [x] Acceptance criteria and verification commands are explicit.
- [x] No product, API, data, or architecture decisions are required.

## Relevant Files And Modules

- `src/copia/**`
- `tests/**`
- `client/src/**`
- `docs/reports/test-integrity/**`

## Dependencies

- AI SDLC harness migration and dependency installation.

## Verification

```bash
./harness/scripts/lint.sh
./harness/scripts/test.sh
./harness/scripts/build-check.sh
./harness/scripts/architecture-check.sh
./harness/scripts/check.sh
```

## Risks

- Large mechanical diffs can hide accidental behavior changes; review formatter-only and manual fixes separately.
- Formatting existing tests triggers the repository Test Integrity Gate even when assertions remain unchanged.

## Sources

- User request: enable conventional strict linting now and perform compliance refactoring separately.
- Repository: `pyproject.toml`, `client/eslint.config.js`, `client/.prettierrc.json`, and harness policies.
