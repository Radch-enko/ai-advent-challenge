# Skeptic perspective

The current session lock is held across provider I/O, so a pause endpoint that tries to acquire that lock can deadlock behind the active request. A control path must update task control state independently and the worker must observe it at safe checkpoints. New messages must be rejected while a task is active.

Changing the existing synchronous `/messages` response to `202` would be a breaking API decision and would disturb existing tests. Additive task endpoints or a synchronous compatibility facade are safer for the MVP.

The main correctness risk is duplicate work: `Agent.ask` is monolithic and mutates the transcript during execution. Persist task identity and original instruction, checkpoint stage/step, and ensure resume does not append another user message. In-process execution plus JSON persistence is enough for browser reload and an explicit resume, but not full process-crash recovery or exactly-once provider invocation.

The UI must not label the control as a hard Stop when the provider transport cannot cancel an in-flight call. Use Pause/Pausing and only show Resume after the persisted state reaches paused.

