# Realist perspective

Use a small `TaskState` domain model stored as an optional field of `ChatSession`, with deterministic stage/step/action values. The smallest honest flow is `planning.prepare`, `execution.agent_ask`, `validation.check`, and `done`. Status is orthogonal: running, pause_requested, paused, failed, or done.

Expose additive endpoints to start, get, pause, and resume a task. Start returns `202` and a task identity; polling returns stage, current step, expected action, status, and progress. Resume takes only the session/task identity and reads the original instruction from persistence. Keep the existing synchronous message endpoint for compatibility or route it through a synchronous facade without changing its public contract.

Verification should cover the transition matrix, JSON round-trip for old sessions, pause/resume without duplicate transcript entries, one active task per session, and client typecheck/build/lint. The UI should poll only while active and restore a paused task after reload.

