# Task: Copia task state machine

## User request

Implement Day 13 for Copia: a deterministic task state machine exposing task stage, current step, and expected action. Use the stages `planning`, `execution`, `validation`, and `done`; support pausing at any safe point and resuming without asking the user to repeat the original instruction. Update the UI so execution can be stopped/paused, progress is visible, and the control becomes resume when paused. Prepare a Figma prompt for the design. Keep the implementation minimal and do not expand into security/privacy work.

## Repository facts

- `POST /sessions/{session_id}/messages` currently holds a per-session lock through provider I/O and returns only after the response is saved.
- `ChatSession` is persisted as JSON but has no task-state field.
- `Agent.ask` contains the current orchestration as one synchronous domain operation.
- `App.tsx` disables the composer while a request is pending and currently has no pause/resume control or task progress view.
- There is no `docs/product/` directory; product basis is limited to the user request and existing Copia architecture.

## Decision to evaluate

Choose between a minimal synchronous stage wrapper, a durable cooperative task runner, and a fully cancellable streaming worker. The hard requirement is resumability without resending the instruction, while keeping scope small.

