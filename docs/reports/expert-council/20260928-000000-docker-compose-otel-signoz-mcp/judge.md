# Council Judge Report

## Decision

Разрешено только безопасное implementation planning; переход к реализации сейчас запрещён до закрытия deployment
contract, telemetry scope, SSRF policy, body representation и retention behavior.

Recommended baseline: optional Compose overlay; `COPIA_OTEL_ENABLED=false`; body capture as a separate opt-in; external
configurable SigNoz; current browser → backend → MCP flow unchanged; no claim of full browser distributed tracing.

## Rationale

This preserves Copia's local-first, single-user product context and current non-Docker development path. It keeps OTel
backend-neutral and treats existing MCP streaming, pinning, redirect rejection, response-size limits, and SSRF checks as
invariants. The council consistently identified custom `httpx2`, payload privacy, Docker networking, and retention as
the highest-risk areas.

## Tradeoffs

- External SigNoz reduces mandatory infrastructure but requires separate setup.
- OTel/body capture off by default protects compatibility and privacy but requires explicit diagnostics enablement.
- Bounded events/logs are safer than a single large span attribute but require storage/query decisions.
- Server-side correlation is simpler than browser tracing but is not a full browser distributed trace.
- A dedicated `httpx2` wrapper preserves invariants but needs specialized tests.

## Required Guardrails

Redact before truncation and export; use structured, failure-safe redaction; cap request and response separately at 64
KiB bytes; skip binary payloads; mark truncation; avoid a single large span attribute; preserve async streaming,
cancellation, pinning, redirect rejection, response limits, and SSRF validation; use a narrow explicit Docker trust rule;
do not expose SigNoz/OTLP/ClickHouse unintentionally; document retention/deletion; keep Compose optional and current SSE,
reconnect, and approval flows compatible.

## Acceptance Criteria

With OTel off, current scripts and behavior remain supported. With OTel on, in-memory tests cover FastAPI, standard HTTP,
and custom `httpx2`; JSON/text request and response bodies are redacted and byte-capped; binary is skipped; transport
invariants and Compose browser → backend → MCP (including SSE/reconnect) are tested; SigNoz is configurable and not
required in CI; Russian docs cover startup, opt-out, exposure, retention/deletion, and rollback.

## Follow-up Checks

Resolve Compose optionality, process/direction scope, browser tracing scope, OTLP contract, host/internal ports, narrow
SSRF rule, event versus log representation, retention/deletion, parse/redaction failure behavior, request/response
separate toggles, duplicate log policy, current-path verification, and resource overhead limits.

## Assumptions

The MCP Streamable HTTP endpoint exists; SigNoz is separately installed; browser tracing is out of scope unless explicitly
expanded; 64 KiB means bytes per request/response; telemetry must not retain secrets.

## Known Risks

Payloads add a second local persistence surface; redaction can miss unusual secrets; generic instrumentation may break
`httpx2`; long streams/workers can lose correlation; Docker DNS conflicts with SSRF/DNS pinning; Compose adds resource
and startup cost; exposed ports can leak telemetry; retention remains unsafe if unspecified; live SigNoz behavior is not
verified by unit tests.

## Confidence

Средняя: guardrails and direction are strongly supported, but implementation readiness is low until the listed blocking
questions are answered.
