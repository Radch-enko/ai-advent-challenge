from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AgentLogBodyResponse(BaseModel):
    content: str
    encoding: Literal["utf-8", "base64"]
    size_bytes: int
    truncated: bool = False
