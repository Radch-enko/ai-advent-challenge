# Skeptic Perspective

The interaction endpoints differ in lifecycle, not only URL: `/messages` completes synchronously and returns response plus duration and memory/summarization side effects; `/turns` returns `202`, tracks a runtime operation, emits SSE, and may wait for approval. A unified lifecycle is sound, but a flat response with many optional fields or a promise that all future behavior is just another response field is not.

Do not centralize unrelated entities behind a universal CRUD or `/actions` endpoint. It would move dispatch, authorization, validation, and error differences into a weakly typed request body. Agent profiles and user profiles are different concepts; working memory, pending suggestions, and profile long-term memory have different semantics; task transitions and MCP approval are commands, not CRUD.

Global and session invariants are the strongest consolidation candidate because their CRUD operations are structurally similar, but their scope and ownership must remain explicit. Scheduled endpoints currently expose read projections, not a CRUD collection. MCP discovery/test have side effects and deserve explicit command semantics.

Use common conventions and typed envelopes where contracts genuinely match. Before migration, define sync/async behavior, state retention, event replay, retry/idempotency, and client compatibility.
