# Critique round

All perspectives recommend a durable cooperative runner. The key disagreement is naming and the exact API shape, not the core architecture. The critique resolves it as follows:

- Keep the task API additive to protect the existing synchronous contract.
- Model `pause_requested` separately from `paused`; a provider call already in progress cannot be force-cancelled.
- Store only the minimal task continuation data needed to resume without a new prompt. Do not attempt to split the existing `Agent.ask` into provider-specific substeps in Day 13.
- Treat process-crash recovery and exactly-once external invocation as known MVP limitations, not hidden guarantees.
- Use `Pause` in the UI and reserve `Stop` for a future true cancellation operation.

