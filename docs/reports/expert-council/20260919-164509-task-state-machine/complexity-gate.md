# Complexity Gate

```yaml
council_required: true
score: 9
reasons:
  - public API changes: 2
  - architectural migration from synchronous request execution to resumable task execution: 2
  - several materially different implementation options: 2
  - cross-module impact across domain, API, persistence, and client: 1
  - high uncertainty around cooperative pause semantics and provider cancellation: 2
```

Security/privacy impact is intentionally out of scope for this task per the user request and contributes zero points.

