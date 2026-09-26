from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from copia.profile_memory.domain.models.memory_category import MemoryCategory
from copia.session_memory.domain.models.memory_action import MemoryAction


class MemoryCandidate(BaseModel):
    scope: Literal["none", "working", "long_term"]
    action: MemoryAction
    category: MemoryCategory | None = None
    key: str = Field(min_length=1, max_length=80)
    value: str | None = Field(default=None, max_length=1_000)
    target_id: str | None = Field(default=None, min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_action(self) -> MemoryCandidate:
        if self.scope == "long_term" and self.category is None:
            raise ValueError("Long-term candidates require a category")
        if self.scope == "long_term" and self.action in {"create", "update"} and not self.value:
            raise ValueError("Long-term create and update candidates require a value")
        if self.action == "delete" and not (self.target_id or self.key):
            raise ValueError("Delete candidates require a key or target_id")
        if self.scope == "none" and self.action != "skip":
            raise ValueError("None candidates must be skipped")
        return self
