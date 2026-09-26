from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.sessions.api.models.session_message_response import SessionMessageResponse


class McpTurnResponse(BaseModel):
    id: str
    session_id: str
    status: Literal["running", "waiting_for_approval", "completed", "failed"]
    approval: McpApproval | None = None
    result: SessionMessageResponse | None = None
    error: str | None = None
