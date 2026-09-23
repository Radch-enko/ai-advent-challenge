# Отчёт Test Integrity

## Резюме

- Task: `local-mcp-http`
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: `tests/test_mcp_local_development.py`
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `MERGED`

## Обоснование

- Reason Category: `SPECIFICATION_CHANGED`
- Why The Test Changed: User explicitly changed the local MCP opt-in default after the original behavior was delivered.
- Old Expected Behavior: Loopback MCP discovery was enabled only when `COPIA_ALLOW_LOCAL_MCP=true`.
- New Expected Behavior: Loopback MCP discovery is enabled when the variable is absent and disabled only by
  `COPIA_ALLOW_LOCAL_MCP=false`.
- Affected Acceptance Criteria: Copia local MCP discovery default and environment override.
- Specification Changed: `YES`
- Incorrect Artifact: `PRODUCTION_CODE`

## Согласование удаления

- Existing Test Deleted: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`
- Approval Evidence: Not applicable; coverage is updated, not removed.

## Оценка ревьюера

- Is The Justification Valid: `YES`; the user explicitly changed the security default.
- Does The Test Still Protect The Same Behavior: `NO`; it intentionally protects the replacement default and explicit
  disable override while the separate endpoint validation tests preserve network restrictions.
- Was Production Code Incorrectly Avoided: `NO`.
- Should Production Code Have Been Fixed Instead: `YES`; production code was changed together with the expectation.
- Notes: Approval notes the accepted residual risk that loopback discovery no longer requires opt-in.

## Evidence

- Diff Evidence: `COPIA_ALLOW_LOCAL_MCP` default changed to enabled; test now verifies absent variable and exact `false`.
- Verification Commands: `.venv/bin/python -m pytest -q tests/test_mcp_client.py tests/test_mcp_api.py
  tests/test_mcp_local_development.py`; Ruff check/format; `./harness/scripts/security-check.sh`.
- Related Production Changes: `src/copia/api/service.py`
