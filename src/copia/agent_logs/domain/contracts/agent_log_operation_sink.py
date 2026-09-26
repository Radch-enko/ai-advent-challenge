from __future__ import annotations

from typing import Protocol, runtime_checkable

from copia.agent_logs.domain.models.agent_log_operation import AgentLogOperation


@runtime_checkable
class AgentLogOperationSink(Protocol):
    def append_operation(self, operation: AgentLogOperation) -> None: ...
