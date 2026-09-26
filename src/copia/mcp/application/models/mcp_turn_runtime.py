from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from copia.mcp.domain.models.mcp_approval import McpApproval


@dataclass
class McpTurnRuntime:
    id: str
    session_id: str
    status: str = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    approval: McpApproval | None = None
    result: Any = None
    error: str | None = None
    decision: bool | None = None
    decision_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)
    audits: list[dict[str, Any]] = field(default_factory=list)
