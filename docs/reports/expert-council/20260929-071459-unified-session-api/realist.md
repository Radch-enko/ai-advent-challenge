# Realist Perspective

There are two viable entry-point choices:

1. Keep `POST /sessions/{id}/messages` as canonical for lower initial migration cost, but return a unified operation envelope that supports both completed and running work.
2. Make `POST /sessions/{id}/turns` canonical for a cleaner lifecycle model that already matches asynchronous MCP execution.

The second is conceptually stronger, provided all the fields now returned by `SessionMessageResponse` are carried in the turn result and clients can handle asynchronous ordinary messages. Keep `/messages` temporarily as a deprecated adapter, then remove it only after clients and compatibility policy are addressed.

Do not merge distinct resources into a generic endpoint. Standardize CRUD shapes and error/pagination conventions, and consider consolidating global/session invariant handling only if explicit scope remains clear. Keep state-machine commands such as pause, resume, retry, approve, and reject explicit. Scheduled status/latest endpoints are read models, not CRUD.

An incremental design review should precede implementation: inspect clients, turn persistence and event replay, OpenAPI, and the existing sync-versus-async behavior.
