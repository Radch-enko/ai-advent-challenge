from __future__ import annotations

from pydantic import BaseModel, Field


class TaskStartRequest(BaseModel):
    instruction: str = Field(min_length=1)
