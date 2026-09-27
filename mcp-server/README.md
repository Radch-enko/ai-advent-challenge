# Copia Finances MCP Server

LLM-neutral MCP server exposing four tools over standard stdio and Streamable HTTP transports:

- `search_expenses` searches and paginates expenses;
- `compare_expense_periods` deterministically compares two expense periods;
- `save_expense_chart` renders a comparison as PNG image content;
- `add_expense` creates one expense.

The comparison and chart tools are provider-independent. The MCP client stores returned PNG artifacts in Copia's
session-scoped artifact storage and appends the chart to the final assistant message.

The server delegates storage to the Copia FastAPI backend. Start the backend first and make sure
`~/.copia/files/finances.xlsx` has the expected `Expenses` sheet and headers.

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e .
```

## Run

```bash
COPIA_API_URL=http://127.0.0.1:8000 .venv/bin/copia-finances-mcp
```

`COPIA_API_URL` is optional and defaults to `http://127.0.0.1:8000`. Configure an MCP client to launch the command
above as a local stdio server. No model- or provider-specific configuration is required.

For local discovery from the Copia MCP screen, run:

```bash
COPIA_API_URL=http://127.0.0.1:8000 .venv/bin/copia-finances-mcp --transport streamable-http
```

The endpoint is fixed to `http://127.0.0.1:8001/mcp`. Local MCP discovery is enabled by default; set
`COPIA_ALLOW_LOCAL_MCP=false` on the Copia backend to disable it.
