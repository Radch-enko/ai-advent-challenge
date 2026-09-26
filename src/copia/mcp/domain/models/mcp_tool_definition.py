from typing import Any

from pydantic import BaseModel, Field


class McpToolDefinition(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
