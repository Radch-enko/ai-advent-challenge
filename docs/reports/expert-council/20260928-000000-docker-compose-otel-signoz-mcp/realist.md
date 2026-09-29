# Realist Perspective

## Recommendation

Proceed only as bounded, additive, opt-in infrastructure. Keep the current `restart-dev.sh` path and make
`COPIA_OTEL_ENABLED=false` the default. Treat separately installed SigNoz as an external dependency, not a mandatory
Compose service. Put OTel setup in a dedicated observability module so `service.py` remains a thin composition root and
existing architecture checks continue to pass.

## Feasible phases

1. Add observability dependencies as optional extras and configuration gating.
2. Instrument FastAPI and standard outbound `httpx`; test with an in-memory exporter, not live SigNoz.
3. Add a composing `httpx2` transport wrapper, preserving the existing pinned/limited transport and streaming.
4. Add supplementary frontend/backend/MCP Dockerfiles and Compose configuration, then Russian operational docs.

The custom `httpx2` wrapper and Docker-internal MCP endpoint are gates: prototype the wrapper before integration and
resolve how the existing SSRF guard permits a trusted Compose service without broadly allowing private destinations.


- OTel disabled: existing focused tests and `./harness/scripts/check.sh` remain green.
- OTel enabled: in-memory spans cover FastAPI, standard HTTP, and `httpx2`.
- Redaction/truncation: request and response JSON/text, nested credentials, 64 KiB boundary, and binary skip.
- Transport invariants: redirect rejection, pinning, response-size limit, and async streaming.
- Compose smoke: frontend → backend → MCP works; SigNoz endpoint is configurable and not required for CI.
- Documentation: startup, opt-out, retention/deletion, ports/network, and rollback are Russian and explicit.


The product vision targets one personal user, local data control, provider choice, tools, and practical usefulness. It
does not make observability a user-facing feature. Therefore telemetry must not become mandatory or alter default data
flows. The README's existing local run path and one-process scheduler assumption must remain supported.


Assume the MCP server already exposes the target Streamable HTTP endpoint, SigNoz is installed separately, and frontend
OTel is outside this decision unless distributed browser tracing is explicitly required. Resolve OTLP protocol, event
versus attribute representation, Compose topology/SSRF policy, body retention, and whether Compose is optional overlay
or the recommended run path before implementation.
