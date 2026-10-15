# Feature workflow

1. Use an explicitly supplied task specification when one exists; otherwise use the current user request as task context. Do not select an unrelated backlog task.
2. Read `AGENTS.md`, relevant policies, and affected code. Identify acceptance criteria and verification before editing.
3. For a substantial new feature, present meaningful options and wait for the user's explicit choice.
4. Implement the smallest complete behavior, including errors and necessary tests. Keep adapters at the established boundaries.
5. Apply the test-integrity workflow before changing existing tests.
6. Run focused checks, then `./harness/scripts/check.sh` if the package is initialized. Review the diff and report evidence and remaining risks.
