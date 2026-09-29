# Expert Council Verdict

## Complexity Gate

```yaml
council_required: true
score: 10
reasons:
  - architectural decision (2)
  - security and privacy impact from telemetry payload capture (3)
  - multiple viable instrumentation and Docker networking designs (2)
  - more than three affected areas (1)
  - uncertainty in custom httpx2 instrumentation and SSRF-safe service discovery (2)
```

Full council was run because the independently calculated score is 10 (2 + 3 + 2 + 1 + 2).

## Decision

План implementation одобрен пользователем и закрывает основные scope choices: локальный Compose остаётся optional,
SigNoz устанавливается отдельно, browser → backend → MCP flow сохраняется, scope ограничен backend HTTP traffic, а body
capture ограничен JSON/text и 64 KiB на каждую сторону. Реализация может продолжаться с указанными ниже безопасными
defaults; она не должна расширять scope до browser tracing или включать telemetry в обычном non-Docker запуске.

Baseline: `COPIA_OTEL_ENABLED=false` by default; Compose opts in, while a separate body-capture flag controls payloads;
configurable external SigNoz; body payloads use OTel log records rather than large span attributes; exact Docker MCP
endpoint allowlisting retains DNS pinning and rejects all other private/metadata destinations; parse/redaction failures
omit payload data but keep sanitized metadata; document SigNoz retention/deletion and the additional telemetry copy.

## Why This Wins

This is additive and preserves Copia's current local-first, single-user product context and non-Docker development path.
OpenTelemetry remains backend-neutral, while existing MCP streaming, pinning, redirect rejection, response-size limits,
and SSRF controls remain explicit invariants. It addresses the highest risks without making telemetry mandatory.

## Rejected Alternatives

- Mandatory SigNoz or mandatory Compose runtime.
- OTel or payload capture enabled by default.
- Global private-network/SSRF bypass for Docker services.
- Regex-only redaction.
- Storing 64 KiB in one span attribute.
- Claiming complete browser-to-MCP distributed tracing without propagation tests.
- Replacing the current non-Docker development path.

## Product/Business Basis

`docs/product/vision.md` describes a personal assistant, local data control, provider choice, tools, and practical
usefulness, not mandatory observability. `README.md` defines the current local run path and one-process scheduler
assumption. Therefore observability is developer infrastructure and must not change default data flow or create an
uncontrolled second data store.

## Acceptance Criteria

- OTel-off behavior and `./scripts/restart-dev.sh` remain supported.
- In-memory tests cover FastAPI, standard outbound HTTP, and custom `httpx2` spans when enabled.
- JSON/text request and response capture is separately capped at 64 KiB bytes, redacted before export, and marked when
  truncated; binary payloads are skipped.
- Negative tests cover nested credentials and secret-bearing headers.
- `httpx2` tests preserve streaming, cancellation, pinning, redirects, SSRF policy, and response-size limits.
- Compose smoke tests preserve frontend/browser → backend → MCP, SSE, reconnect, and approval behavior.
- SigNoz is configurable, external, and not required for CI; ports and retention/deletion are documented in Russian.
- Documentation distinguishes preserved request flow from browser distributed tracing.

## Follow-up Checks

Resolved implementation defaults: optional Compose; backend inbound and outbound HTTP only; no browser tracing; gRPC
OTLP to a configurable endpoint defaulting to `http://host.docker.internal:4317` in Compose; host ports remain limited to
the frontend/backend while MCP is internal; exact trusted MCP endpoint `http://mcp-server:8001/mcp`; structured OTel log
records for bounded bodies and spans for metadata; separate OTel/body-capture toggles; fail closed for body parsing or
redaction; document SigNoz's configured retention/deletion and the second payload copy; preserve and test the existing
non-Docker run path.

## Assumptions

The MCP Streamable HTTP endpoint already exists; SigNoz is installed separately; browser tracing is out of scope unless
expanded; 64 KiB means bytes per request/response; and telemetry must never retain secrets.

## Known Risks

Payloads create a second local persistence surface; unusual secrets may evade redaction; generic instrumentation may break
`httpx2`; long streams/workers may lose correlation; Docker DNS may conflict with SSRF/DNS pinning; Compose adds startup
and resource cost; bad host bindings can expose telemetry; unspecified retention is unsafe; and live SigNoz behavior is
not verified by unit tests.

## Confidence

Средняя. Direction and guardrails are strongly supported by all perspectives, but implementation readiness is low until
the blocking questions are resolved.
