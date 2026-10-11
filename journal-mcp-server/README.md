# Copia Journal MCP Server

This MCP server exposes tools for reading and updating a single daily journal note. It delegates storage to the Copia
FastAPI backend; it does not access the knowledge-base filesystem.

## Run

Install the package in a Python 3.11+ environment, then run:

```bash
COPIA_API_URL=http://127.0.0.1:8000 copia-journal-mcp
```

For local MCP discovery, run:

```bash
COPIA_API_URL=http://127.0.0.1:8000 copia-journal-mcp --transport streamable-http
```

The Streamable HTTP endpoint defaults to `http://127.0.0.1:8002/mcp`. Docker Compose runs it on port 8002 and connects
it to the backend over the private Compose network.

## Configure the agent

In Copia MCP settings, add connection ID `journal` with endpoint `http://127.0.0.1:8002/mcp` for local development.
In Docker, use `http://journal-mcp-server:8002/mcp`. Enable `get_daily_journal` and
`apply_daily_journal_changes` for the `daily_journal` agent profile.

Read and write tool calls use Copia's existing MCP approval flow. After a successful edit, the journal remains absent
from RAG until the user manually starts document indexing.
