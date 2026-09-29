# Task

Analyze how to unify Copia's agent interaction endpoints and reduce API fragmentation across CRUD-like features, without implementing changes.

## Context

The user wants one extensible request/response contract for session interactions instead of separate `/messages` and `/turns` entry points, and less CRUD route sprawl across memory, MCP connections, profiles, invariants, and scheduled jobs.

Current implementation has a synchronous `POST /sessions/{session_id}/messages` and an asynchronous MCP `POST /sessions/{session_id}/turns` with status polling, SSE events, and approval handling. The synchronous path rejects MCP-enabled configuration with `409 mcp_turn_required`.

Product context: Copia is a personal assistant centered on agents, tools, saved sessions, user-controlled approvals, and automations. Product vision does not set a fixed roadmap.

## Scope

- Recommend a canonical interaction lifecycle and migration direction.
- Identify which resource routes or commands are meaningful candidates for consolidation.
- Compare risks and alternatives.
- Read-only analysis; no production code changes.
