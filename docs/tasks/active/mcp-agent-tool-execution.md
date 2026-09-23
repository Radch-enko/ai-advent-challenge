# Task

ID: mcp-agent-tool-execution
Status: completed
Title: MCP tool execution for Copia agents

## Goal

Allow Copia agents to use explicitly enabled MCP tools through OpenAI and GigaChat while requiring an inline user
approval before every tool call.

## Context

Copia can currently discover MCP tools but does not persist connections, pass tool schemas to providers, execute
`tools/call`, or expose live tool execution state to the UI. The expenses MCP server is available through Streamable
HTTP and provides the first end-to-end integration target.

## Functional requirements

- Persist MCP connections in `~/.copia/mcp_connections.json`. An `AgentConfig` stores connection references and an
  allowlist of enabled tool names.
- A connection contains `id`, `name`, `endpoint`, optional `header_name` and `header_value_env`, cached server metadata,
  and the most recently discovered tools. Environment references must start with `COPIA_MCP_`; secret values must not
  be persisted, returned to the frontend, or logged.
- Provide connection CRUD and test/discovery APIs. Reject deletion while a connection is referenced by an active
  configuration.
- Rediscover schemas before every tool-enabled turn and expose only enabled tools to the selected provider. Provider
  aliases must be stable, collision-safe, and at most 64 characters.
- Support provider-native tool calls for OpenAI and GigaChat through provider-neutral domain contracts.
- Require approval for every tool call. Rejection returns `User rejected this tool call` to the model without invoking
  MCP. Process calls sequentially and stop after eight calls per LLM turn.
- Execute approved calls through MCP `tools/call`, return bounded structured results to the model, and treat remote
  content as untrusted.
- Add asynchronous session turn APIs with status lookup, SSE events, and an approval endpoint. Emit `turn_started`,
  `tool_approval_required`, `tool_running`, `tool_completed`, `final`, and `error` events.
- Keep approvals pending without a timeout and reject a new turn in the same session while one is active. Mark
  interrupted turns and tasks failed after backend restart.
- Support MCP tool calls in normal chat and every Task mode LLM stage, but not in summarization, facts update, or memory
  classification calls.
- Keep the synchronous message endpoint compatible for agents without MCP; return `409` for MCP-enabled configurations.
- Store bounded tool arguments and results plus server/tool, decision, status, and duration in agent logs without
  storing credentials.
- Update the MCP UI into a connection registry editor and add per-agent connection/tool selection.
- Show an inline approval card with server, tool, and arguments. While an approved call runs, show
  `Выполняю {tool_name}`. Restore pending state after reconnect and expose the same interaction in Task mode.

## Non-functional requirements

- Preserve current SSRF, DNS pinning, redirect, timeout, proxy, response-size, and error-redaction protections.
- Registry and runtime state remain outside Git.
- MCP behavior stays provider-neutral outside provider adapters.
- Existing non-MCP agent behavior remains unchanged.

## Out of scope

- Automatic execution without confirmation.
- Durable continuation of a partially completed provider/tool loop across backend restart.
- Authentication secrets stored in application JSON or sent back to the browser.
- Parallel tool execution.

## Acceptance criteria

- [x] Connections can be created, tested, listed, updated, and safely deleted through API and UI.
- [x] Agents expose only explicitly enabled tools from referenced connections.
- [x] OpenAI and GigaChat receive valid native tool definitions and tool-result messages.
- [x] Approve executes MCP and continues the model loop; reject skips MCP and still produces a final model response.
- [x] A ninth tool request fails with a bounded, user-facing error.
- [x] Chat and Task mode expose persisted pending approvals and live execution states.
- [x] UI displays `Выполняю {tool_name}` only while the MCP call is running.
- [x] MCP credentials are neither persisted nor exposed through API responses or logs.
- [x] Existing agents without MCP keep their current behavior.
- [x] Focused tests and repository checks pass, or exact unrelated failures are documented.

## Relevant modules

- `src/copia/domain/models`
- `src/copia/domain/services`
- `src/copia/data/providers`
- `src/copia/data/mcp_client.py`
- `src/copia/api/service.py`
- `client/src`
- `tests`

## Constraints

- Python 3.11+, FastAPI, React/TypeScript, official MCP SDK.
- OpenAI and GigaChat are both required in v1.
- Approval has no timeout; backend restart fails interrupted work.
- Existing tests are not changed or removed without the Test Integrity Gate.

## Verification

- Focused pytest suites for registry, MCP client, providers, tool loop, turn API, and Task mode.
- Frontend typecheck, production build, lint, and focused UI tests where supported.
- `./harness/scripts/architecture-check.sh`
- `./harness/scripts/security-check.sh`
- `./harness/scripts/check.sh`

## Risks

- Full arguments/results audit can persist sensitive financial data by explicit product choice.
- Approval without timeout can retain an active in-memory worker indefinitely.
- Provider-native function calling differs between OpenAI and GigaChat and requires adapter-specific serialization.

## Open questions

None.
