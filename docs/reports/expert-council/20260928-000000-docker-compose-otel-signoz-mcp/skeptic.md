# Skeptic Perspective

## Core concerns

The requested body capture creates a critical privacy boundary: MCP arguments and provider payloads may contain user
data, credentials, or tokens. A regex-only redactor can miss nested JSON, custom credential fields, encoded values, or
non-UTF-8 data. Redaction must happen before truncation and before any OTel attribute/event/export operation, with
negative tests proving secrets never reach telemetry.

The custom `httpx2` transport is not equivalent to `httpx` event hooks. A generic httpx instrumentor can leave MCP
calls untraced or break stream semantics. Instrument it with a composition wrapper that preserves pinning, redirect
rejection, response-size limits, and the existing async stream behavior. Binary content must not be treated as JSON/text.

Do not put an unbounded 64 KiB payload into a single span attribute. Use a bounded event or log representation, document
backend limits, and record truncation/content-type metadata. Avoid duplicate storage with existing redacted agent logs,
or define the duplication policy explicitly.

## Deployment and privacy hazards

SigNoz/ClickHouse adds a second local persistence location for user data. It should be opt-in, have documented retention
and deletion behavior, and not be exposed broadly through host ports. OTLP endpoints and SigNoz UI should be internal or
explicitly protected. Docker service names may resolve to private addresses rejected by the existing MCP SSRF guard;
the chosen exception must not silently weaken SSRF protection.

The MCP server's own outbound HTTP calls may need instrumentation for a genuinely complete trace. Long-lived SSE and
async worker spans may otherwise be disconnected. Compose also adds startup/resource friction and must not silently
replace the existing non-Docker development path.


- secret-bearing headers and nested JSON are absent from exported spans/events;
- JSON/text capture is capped at 64 KiB, binary payloads are skipped, and truncation is explicit;
- MCP streaming, size limits, pinning, redirects, and SSRF protections remain intact;
- SigNoz is not accidentally internet/LAN exposed;
- telemetry-disabled operation preserves current behavior;
- MCP client and MCP-server outbound calls are covered if end-to-end tracing is claimed.
