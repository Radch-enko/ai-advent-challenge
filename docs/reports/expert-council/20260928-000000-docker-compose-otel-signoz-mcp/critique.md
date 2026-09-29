# Critique Round

## Findings

The perspectives agree that this must be additive and opt-in: preserve `./scripts/restart-dev.sh`, default OTel off,
and treat separately installed SigNoz as an external dependency. Body capture must be content-type-aware, bounded,
redacted before truncation/export, and not a single 64 KiB span attribute. The custom `httpx2` wrapper must preserve
streaming, cancellation, pinning, redirect rejection, and response-size limits.

The major unresolved architecture questions are: how a Docker service name can pass the existing SSRF policy without a
general private-network bypass; whether the body is an event or log record; whether scope includes MCP-server outbound
HTTP and browser distributed tracing; and how Compose preserves host-browser access, proxying, SSE, and reconnects.

## Corrections required before implementation

- The supplied score 7 must be treated as an explicit user routing decision; if recalculated from the rubric, record the
  exact criteria and arithmetic rather than implying the three listed reasons alone sum to seven.
- “Approved plan” is a user-provided description, not independently verified repository evidence.
- “Local/self-hosted” does not by itself prove safe retention or access control.
- “End-to-end trace” must distinguish a backend-to-MCP-client span from propagation through the MCP server and its
  outbound calls.
- A 64 KiB limit must specify bytes versus characters and separate request/response behavior.

## Decision questions for the judge

1. Is Compose an optional overlay, and is OTel disabled by default with body capture separately opt-in?
2. Which processes and HTTP directions are in telemetry scope?
3. Is server-side correlation sufficient, or is browser distributed tracing required?
4. Which OTLP protocol/endpoint contract and host/internal ports are supported?
5. What narrow trust mechanism permits the Compose MCP endpoint while retaining SSRF protections and TLS/DNS behavior?
6. Are payloads events or logs, what are their retention/deletion semantics, and what happens on parse/redaction failure?
7. How will current non-Docker and browser → backend → MCP behavior be verified?

## Recommendation

Do not implement until deployment contract, telemetry scope, SSRF policy, payload representation, and retention behavior
are explicit. The safe baseline is optional Compose, OTel and body capture off by default, external configurable SigNoz,
structured failure-safe redaction, bounded event/log payloads, isolated `httpx2` tests, and acceptance tests for both
current and Compose flows.
