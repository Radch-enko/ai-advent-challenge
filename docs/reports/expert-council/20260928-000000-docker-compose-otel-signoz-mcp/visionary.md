# Visionary Perspective

## Product value

OpenTelemetry can make Copia less of a black box: a local trace can explain latency and failures across FastAPI,
provider HTTP, and MCP. This supports trust, debugging, and reliability for the personal assistant. The standard also
keeps a future change of telemetry backend possible without coupling application code to SigNoz.

## Strategic and architectural recommendation

Use local, self-hosted observability consistent with the product's local-data principle, while preserving the existing
browser → backend → MCP orchestration boundary. Deliver in phases: Compose/runtime foundation; FastAPI and standard
HTTP instrumentation; custom `httpx2` MCP transport instrumentation; then payload capture and redaction. Make payload
capture privacy-aware and keep it close to the source of data.

## Acceptance criteria

- SigNoz can show a trace from FastAPI through outbound MCP HTTP.
- JSON/text bodies are captured only up to 64 KiB and secrets are redacted.
- Compose services communicate on their intended network without changing the browser/backend/MCP path.
- Telemetry overhead and retention are measured and documented.

## Risks and open questions

Body capture may add memory, CPU, and storage pressure; streaming MCP responses are difficult to instrument; SigNoz
may be heavy for a single-user local setup; retention policy is unspecified; and it is unresolved whether body data
belongs in span attributes, span events, or logs. The team must also decide whether SigNoz is bundled, external, or
optional, and whether standard HTTP instrumentation is sufficient for `httpx2`.

## Disagreements to test

- Full body capture versus event/log records.
- Automatic FastAPI/httpx instrumentation versus explicit middleware.
- Redaction at the transport boundary versus a later telemetry processor.
