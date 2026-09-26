class ScheduledJobFailure(RuntimeError):
    def __init__(self, message: str, agent_log_id: str | None = None) -> None:
        super().__init__(message)
        self.agent_log_id = agent_log_id
