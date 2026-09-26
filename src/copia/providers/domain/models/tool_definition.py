from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
