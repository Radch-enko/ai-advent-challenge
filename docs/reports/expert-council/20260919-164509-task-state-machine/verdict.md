## Complexity Gate

`council_required: true`, score `9`. Reasons: public API, architectural migration, cross-module impact, multiple viable designs, and uncertainty around pause semantics. Security/privacy is explicitly out of scope.

## Decision

Implement a durable cooperative runner with optional `TaskState` in `ChatSession`, fixed steps `planning.prepare` → `execution.agent_ask` → `validation.check` → `done`, additive start/get/pause/resume endpoints, persisted instruction/checkpoints, and polling UI. Keep the existing `/messages` contract unchanged.

Pause is cooperative and safe-point based. It must not wait for the current provider call or the long message lock; with current synchronous providers it becomes `paused` after the in-flight call reaches a checkpoint.

## Why This Wins

It is the smallest approach that genuinely enables resume without repeating the instruction, preserves compatibility, and makes progress deterministic and visible.

## Rejected Alternatives

- Synchronous stage wrapper: cannot provide real pause/resume.
- Fully cancellable streaming worker: unsupported by current provider transport and oversized for Day 13.
- Changing `/messages` to async `202`: breaking API migration outside the minimal scope.

## Product/Business Basis

No `docs/product/` documents exist. The basis is the user’s Day 13 requirements and existing Copia architecture. The MVP promises observable progress and resumability, not hard cancellation, process-crash recovery, or exactly-once provider execution.

## Acceptance Criteria

- Deterministic stage/step/action values and valid transition matrix.
- Old session JSON loads without task state.
- Resume uses persisted instruction and does not duplicate the user message.
- Pause returns quickly as requested and becomes `paused` at a safe point.
- Only one active task per session.
- UI restores paused state after reload and shows Resume.
- Backend transition/persistence/pause-resume/duplicate tests and client checks pass.
- Existing `/messages` contract remains compatible.

## Follow-up Checks

Test transition matrix, pause during provider I/O, JSON lost-update races, duplicate prevention, focused tests, and `./harness/scripts/check.sh`.

## Assumptions

Execution remains in-process. Persisted checkpoints cover browser reload and explicit resume; process-crash recovery is out of scope.

## Known Risks

Pause latency may equal the current synchronous provider call. Incorrect checkpoint/transcript synchronization can cause lost updates and must be covered by tests.

## Confidence

High, `0.88`.

