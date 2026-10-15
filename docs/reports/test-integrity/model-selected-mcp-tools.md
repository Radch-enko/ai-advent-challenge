# Test Integrity Report

## Summary

- Task: Replace keyword-based Git tool routing with model-selected MCP tool calls.
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: `tests/test_service.py`, `tests/test_git_help.py`
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `PENDING`

## Rationale

- Reason Category: `SPECIFICATION_CHANGED`
- Why The Test Changed: The user explicitly requires the LLM to receive MCP-derived tool schemas and choose which Git tools to call. Existing expectations encode the superseded keyword router and direct branch response.
- Old Expected Behavior: `/help` reads the branch before model generation; keyword matches select status, history, or diff; branch-only and empty-documentation questions may skip chat entirely.
- New Expected Behavior: Every `/help` request presents discovered tool schemas to the chat model. A model-requested, allowlisted tool is executed through MCP and its result returned for the final answer. No keyword router or direct branch shortcut remains.
- Affected Acceptance Criteria: Model chooses among MCP Git tools; documentation retrieval and citation validation remain in place; unrequested tools are not executed.
- Specification Changed: `YES`
- Incorrect Artifact: `PRODUCTION_CODE`

## Deletion Approval

- Existing Test Deleted: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`
- Approval Evidence: Not applicable; obsolete expectations are replaced with assertions for the new behavior.

## Reviewer Assessment

- Is The Justification Valid: `YES`
- Does The Test Still Protect The Same Behavior: `YES`, for repository facts, citation validation, and MCP failure handling; tool-selection ownership changes by specification.
- Was Production Code Incorrectly Avoided: `NO`
- Should Production Code Have Been Fixed Instead: `YES`; production routing is being replaced.
- Synthetic Test Data Review: `YES`
- Synthetic Test Data Evidence: Test repositories, paths, branch names, and responses remain invented fixtures.
- Notes: No test is deleted or disabled. The change is subject to static review; test execution was not requested for this task.

## Evidence

- Diff Evidence: Existing test cases will be retained and their expectations updated to reflect model-selected calls.
- Verification Commands: Static lint and type checks only; automated tests were not requested.
- Related Production Changes: `src/code_assistance/service.py`, `mcp_client.py`, `providers.py`, `models.py`, `ports.py`, and `cli.py`.
