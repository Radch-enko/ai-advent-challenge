from typing import Any, Literal

from pydantic import BaseModel


class McpApproval(BaseModel):
    id: str
    connection_id: str
    connection_name: str
    tool_name: str
    arguments: dict[str, Any]
    decision: Literal["pending", "approved", "rejected"] = "pending"
