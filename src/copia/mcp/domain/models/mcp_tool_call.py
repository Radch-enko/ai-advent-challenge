from typing import Any

from pydantic import BaseModel


class McpToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]
