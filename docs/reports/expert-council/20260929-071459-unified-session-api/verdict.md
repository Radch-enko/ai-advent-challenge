# Verdict: Unified Session API

## Complexity Gate

Score 9: public API change (2), architectural migration (2), multiple viable designs (2), more than three modules affected (1), and high uncertainty (2). Full council was required and completed.

## Decision

Make `/sessions/{session_id}/turns` the target entry point for every interaction with the session agent. A turn should carry a typed result, status, events, and approval state. Keep `/messages` temporarily as a compatibility adapter while the client migrates.

For CRUD, preserve domain-specific resource routes. Unify conventions and shared scope semantics rather than routing all entities through one generic CRUD endpoint. Review global/session invariants as a focused follow-up.

## Why This Wins

Today `/messages` is synchronous and returns model output plus duration and memory/summarization effects. `/turns` is asynchronous and supports status polling, SSE, and MCP approval; the message route rejects MCP-enabled sessions. One turn lifecycle removes this semantic split and provides a place for future interaction results without creating another message-entry endpoint.

Typed per-domain CRUD remains clearer and safer because profiles, memory types, MCP connections, tasks, and scheduled-job projections have different ownership, lifecycle, and side effects.

## Rejected Alternatives

- Keep `/messages` for regular chat and `/turns` for MCP: retains the split.
- Use one `/resources/{kind}` or generic `/actions` endpoint for every feature: moves complexity into weakly typed dispatch and hides domain rules.
- Treat state transitions as generic PATCH operations: loses explicit command semantics.
- Migrate everything in a single breaking release: adds avoidable client risk.

## Product/Business Basis

The product vision prioritizes a personal assistant with specialized agents, tools, saved sessions, user-controlled approvals, and automations. A turn models a complete interaction across those capabilities. The vision defines no fixed roadmap or need for universal CRUD.

## Acceptance Criteria

1. Normal messages and MCP-enabled work share one canonical turn creation endpoint.
2. The turn contract represents quick completion and ongoing asynchronous execution.
3. Existing `/messages` result fields remain available in the typed turn result.
4. Events and approvals are tied to the same turn lifecycle.
5. Client migration from `/messages` is explicit and the legacy route remains until clients move.
6. CRUD conventions are consistent where semantics match, while distinct resources and commands remain typed.

## Follow-up Checks

- Inspect frontend callers and confirm compatibility requirements.
- Specify completion status/HTTP codes, persistence, replayable SSE, retries/idempotency, and errors.
- Map current message result fields into turn result and verify approval behavior.
- Review API schema and invariant scoping before an implementation task.

## Assumptions

- A turn can represent an ordinary message even when it completes quickly.
- The user wants an extensible interaction contract, not a universal API endpoint for unrelated resources.
- A staged migration is acceptable.

## Known Risks

- The client may need asynchronous state handling for ordinary messages.
- Current turn state may need stronger persistence and reconnect semantics.
- The response schema can become over-generalized if future fields are added speculatively.
- Consolidating invariant routes without clear scope rules could blur global and session behavior.

## Confidence

High for unified turn lifecycle and typed domain resources. Medium-high for choosing `/turns` over `/messages` as canonical until client usage and compatibility policy are confirmed.
