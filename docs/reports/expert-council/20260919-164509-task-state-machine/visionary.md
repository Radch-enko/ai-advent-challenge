# Visionary perspective

The task state machine gives Copia a product-level explanation of what the assistant is doing instead of exposing only a loading indicator. It makes long-running personal-assistant work legible: the user can see whether Copia is preparing context, executing the main operation, or validating the result, and can return to a paused task without restating the request.

The MVP should remain coarse-grained because `Agent.ask` is currently one synchronous operation. A durable cooperative runner with persisted state and polling provides the UX foundation without introducing a new provider streaming contract. The UI should show a stage stepper, current step, expected action, and explicit Pause/Resume states. A fully cancellable streaming worker would be future work rather than a Day 13 requirement.

The product promise must be worded honestly: pause is cooperative and takes effect at the next safe checkpoint when a provider call is already in flight.

