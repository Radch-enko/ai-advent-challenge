from __future__ import annotations

from typing import Protocol, runtime_checkable

from copia.agent_logs.domain.models.agent_log_exchange import AgentLogExchange


@runtime_checkable
class AgentLogSink(Protocol):
    """Minimal provider logging contract used by domain routing composition."""

    max_body_bytes: int

    def append(self, exchange: AgentLogExchange) -> bool: ...
