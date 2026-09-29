# Critique Round

The perspectives agree that the main opportunity is to unify the interaction lifecycle, while preserving domain-specific resource routes. The disagreement is whether the canonical POST should remain `/messages` to minimize migration or become `/turns` to represent the asynchronous operation lifecycle consistently.

The implementation already gives `/turns` a stable operation identity, status, event stream, and approval lifecycle. Conversely, `/messages` has richer synchronous result data and is likely more familiar to current clients. The deciding factor is whether ordinary messages should become lifecycle objects even when they finish quickly.

Recommended compromise: choose `/turns` as the target contract because it naturally covers both synchronous completion and long-running/tool-mediated execution; retain `/messages` only as a temporary adapter during migration. The response must preserve the existing message result fields in a typed `result`, while operation status/events/approval stay first-class. Do not force every possible future capability into nullable fields; add typed result/event variants as concrete capabilities arrive.

For CRUD, unify only common conventions and clearly shared scope models. Do not create a generic endpoint for heterogeneous resources. Treat global/session invariants as a separate follow-up consolidation candidate, not as a prerequisite for turn unification.
