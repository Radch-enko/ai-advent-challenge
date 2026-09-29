# Visionary Perspective

Unify the user's interaction with an agent as a **turn**. Any input starts one turn, whether it produces a plain model response, invokes MCP tools, waits for approval, or later supports another typed input mode.

```text
POST /sessions/{session_id}/turns
GET  /sessions/{session_id}/turns/{turn_id}
GET  /sessions/{session_id}/turns/{turn_id}/events
POST /sessions/{session_id}/turns/{turn_id}/approvals/{approval_id}
```

Use typed input, result, and event payloads so new interaction capabilities can be represented in the turn contract. Keep events and decisions as follow-up operations because a single HTTP response cannot contain future events or an approval decision.

Keep resources such as profiles, memory, invariants, MCP connections, and scheduled jobs as distinct typed collections. Group them by ownership and scope; preserve explicit commands for operations such as test, discovery, approval, and retry. A generic `/resources/{type}` would weaken validation and documentation.

The main costs are a breaking client migration and defining operation identity, persistence, retry/idempotency, event replay, and error semantics. A temporary `/messages` compatibility adapter can reduce migration risk.
