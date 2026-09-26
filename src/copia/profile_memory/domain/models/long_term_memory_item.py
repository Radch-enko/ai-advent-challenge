from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from copia.profile_memory.domain.models.memory_category import MemoryCategory


class LongTermMemoryItem(BaseModel):
    """A profile-scoped, explicitly user-managed memory record."""

    id: str
    scope: Literal["long_term"] = "long_term"
    category: MemoryCategory
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=1_000)
    created_at: datetime
    updated_at: datetime
