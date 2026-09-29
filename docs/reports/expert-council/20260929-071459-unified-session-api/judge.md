# Council Judge

## Complexity Gate

Score 9: public API change (2), architectural migration (2), multiple viable designs (2), more than three modules affected (1), high uncertainty (2). Full council required.

## Decision

Target one interaction lifecycle around `POST /sessions/{session_id}/turns` for all user inputs. Keep turn status, result, events, and approvals under that lifecycle. Treat `/messages` as a temporary compatibility adapter during client migration.

For other features, retain typed, domain-specific resource URLs and commands. Standardize common CRUD conventions and assess global/session invariants as a focused follow-up; do not introduce generic `/resources/{kind}` CRUD.

## Why This Wins

The current `/messages` and `/turns` endpoints differ in execution lifecycle: one completes synchronously, while the other creates an asynchronous operation with status, SSE, and approval. A turn is the more extensible unit for both. Typed results can preserve response, duration, summarization, facts, and memory data while status and events describe ongoing execution.

Domain-specific routes preserve OpenAPI typing, validation, ownership, and explicit state transitions. This matches Copia's present range of agents, memory, tools, and automation without claiming all features share one lifecycle.

## Rejected Alternatives

- Keep `/messages` canonical and use `/turns` only for MCP: preserves the current split that the user wants removed.
- One generic CRUD endpoint for all resource types: weakens typed contracts and hides domain rules in dispatch logic.
- Replace task/MCP commands with arbitrary status patches: obscures valid state transitions and side effects.
- Rewrite all clients and routes in one step: unnecessary compatibility risk.

## Product/Business Basis

`docs/product/vision.md` describes a personal assistant focused on specialized agents, connected tools, saved sessions, approval control, and automations. A unified turn models one user interaction across these capabilities. The document does not establish a roadmap requiring a universal resource API.

## Acceptance Criteria

1. Normal messages and MCP-enabled interactions use one canonical turn creation request.
2. Turn status, result, events, and approval lifecycle have one typed contract.
3. Existing message result data is preserved in the turn result.
4. The client has a defined migration path from `/messages`.
5. Adding a new interaction mode does not require a parallel message-entry endpoint.
6. Distinct CRUD resources remain typed and domain-specific; their common conventions are documented.

## Follow-up Checks

- Inspect client use of `/messages` and `/turns` and plan a compatibility period.
- Define sync-versus-async response behavior, turn persistence, event replay/cursors, retries/idempotency, and failure representation.
- Confirm MCP approval ownership and preserve message response side effects in the new result.
- Review OpenAPI and global/session invariant scope before implementation.

## Assumptions

- The user values one extensible interaction contract more than preserving synchronous completion as an invariant.
- A turn may complete quickly or remain asynchronous.
- Backward compatibility can be handled with a temporary adapter.

## Known Risks

- Ordinary message UX and client types may need to support operation status.
- The existing in-memory turn lifecycle may not yet satisfy persistence/reconnect requirements.
- Over-generalizing result/event variants can recreate the complexity the design intends to remove.
- Similar CRUD shapes do not imply identical ownership or semantics.

## Confidence

High confidence in unifying the interaction lifecycle and rejecting universal CRUD. Medium-high confidence in `/turns` as canonical because migration cost and client usage should be confirmed before implementation.
