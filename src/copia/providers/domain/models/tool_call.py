from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]
