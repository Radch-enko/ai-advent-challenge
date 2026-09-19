# Council judge

The council approves a durable cooperative runner with an optional persisted `TaskState` in `ChatSession`, fixed deterministic steps, additive task endpoints, and a polling UI. The existing synchronous `/messages` contract should remain unchanged.

Pause is a safe-point operation: the current provider transport is synchronous and cannot interrupt an in-flight provider call. The pause endpoint must not wait for the long-held message lock; it should update task control state independently, and the worker should persist `paused` at the next checkpoint. Resume uses persisted instruction/checkpoint data and must not append a duplicate user message.

