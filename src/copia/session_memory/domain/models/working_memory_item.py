from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkingMemoryItem(BaseModel):
    """A session-scoped key-value record describing the current task."""

    id: str
    scope: Literal["working"] = "working"
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=1_000)
    created_at: datetime
    updated_at: datetime
