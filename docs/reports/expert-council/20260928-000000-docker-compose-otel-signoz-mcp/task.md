# Expert Council Task

## Decision

Evaluate the approved plan to add local Docker Compose for the Copia Vite frontend, FastAPI backend, and Streamable
HTTP MCP server; instrument FastAPI and outbound HTTP, including the custom `httpx2` MCP transport, with OpenTelemetry
exporting to separately installed self-hosted SigNoz; capture JSON/text request and response bodies up to 64 KiB while
redacting credentials and secrets; and write Russian documentation.

## Constraints

- Preserve the current browser → backend → MCP flow.
- Treat repository root `AGENTS.md` and `docs/product/vision.md` as normative context.
- Evaluate security and architecture tradeoffs before implementation.
- Do not edit application code during council.
- All experts and judge are read-only.

## Sources reviewed

- `AGENTS.md`
- `README.md`
- `docs/product/vision.md`
- `.agents/skills/expert-council/SKILL.md`

## Routing

The complexity gate is score 10, so the full Visionary/Skeptic/Realist council, one critique round, and Council Judge are
required before any implementation routing.
