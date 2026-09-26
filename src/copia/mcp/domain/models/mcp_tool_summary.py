from typing import Any

from pydantic import BaseModel, Field


class McpToolSummary(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    input_schema: dict[str, Any] = Field(default_factory=dict)
