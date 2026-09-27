# Test Change Report

- Changed test file: `mcp-server/tests/test_server.py`
- Risk level: Medium
- Reason category: `SPECIFICATION_CHANGED`
- Acceptance criteria: the Finance MCP server exposes `compare_expense_periods` and `save_expense_chart`.
- Old expected behavior: discovery returned exactly `search_expenses` and `add_expense`.
- New expected behavior: discovery also returns the two deterministic pipeline tools while retaining the existing tools.
- Why the test changed: the explicit feature specification adds two public MCP tools.
- Production code or test incorrect: the existing test encoded the previous public tool list; production behavior must expand.
- Reviewer verdict: APPROVED
- Final outcome: preserve the exact-tool-list assertion with the new four-tool contract and add focused behavior tests.
