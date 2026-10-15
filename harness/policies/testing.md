# Testing policy

- Use pytest with temporary fictitious Git repositories and provider fakes. No test may read personal repositories or real credentials.
- Verify behavior at boundaries: repository discovery, path safety, document selection, chunk metadata, index freshness and deletion, retrieval, unsupported answers, provider errors, and MCP tool calls.
- Add regression coverage for bug fixes when practical. Apply `harness/workflows/test-integrity-gate.md` before modifying existing tests; removing existing coverage requires explicit user approval.
- Run focused checks and then `./harness/scripts/check.sh` when the package exists. Do not suppress failures to make the gate pass.
