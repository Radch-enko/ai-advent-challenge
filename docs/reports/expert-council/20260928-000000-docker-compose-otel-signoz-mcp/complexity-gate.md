```yaml
council_required: true
score: 10
reasons:
  - architectural decision (2)
  - security and privacy impact from telemetry payload capture (3)
  - multiple viable instrumentation and Docker networking designs (2)
  - more than three affected areas: backend, MCP server, frontend, Docker, and docs (1)
  - uncertainty in custom httpx2 instrumentation and SSRF-safe service discovery (2)
```

Total: 2 + 3 + 2 + 1 + 2 = 10. Full council is required.
