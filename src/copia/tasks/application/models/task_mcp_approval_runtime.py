import threading
from dataclasses import dataclass, field

from copia.mcp.domain.models.mcp_approval import McpApproval


@dataclass
class TaskMcpApprovalRuntime:
    session_id: str
    task_id: str
    approval: McpApproval
    decision: bool | None = None
    event: threading.Event = field(default_factory=threading.Event)
