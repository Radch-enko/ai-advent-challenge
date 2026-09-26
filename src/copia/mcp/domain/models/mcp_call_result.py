from typing import Any

from pydantic import BaseModel, Field


class McpCallResult(BaseModel):
    content: list[dict[str, Any]] = Field(default_factory=list)
    structured_content: dict[str, Any] | None = None
    is_error: bool = False
