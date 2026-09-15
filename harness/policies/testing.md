# Testing Policy

- Backend tests use pytest under `tests/`; API behavior uses FastAPI `TestClient`.
- Domain and context-management behavior should use deterministic tests and provider fakes.
- Frontend tests are added only when requested behavior cannot be verified by TypeScript, lint, or a production build.
- UI screenshots or visual tests are appropriate only when appearance is part of the contract.
- Do not invent a coverage threshold.
- Minimum evidence is a focused check plus `./harness/scripts/check.sh`, or an exact reason the full gate could not run.
- New tests are low risk. Modifying existing tests requires the Test Integrity Gate; deleting existing coverage requires explicit human approval.
