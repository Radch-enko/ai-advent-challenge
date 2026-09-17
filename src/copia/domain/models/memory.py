from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .config import ProviderTrace

MemoryCategory = Literal["decision", "profile", "knowledge"]
MemoryScope = Literal["short_term", "working", "long_term"]
MemoryAction = Literal["create", "update", "delete", "skip"]


class LongTermMemoryItem(BaseModel):
    """A profile-scoped, explicitly user-managed memory record."""

    id: str
    scope: Literal["long_term"] = "long_term"
    category: MemoryCategory
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=1_000)
    created_at: datetime
    updated_at: datetime


class LongTermMemoryCreate(BaseModel):
    category: MemoryCategory
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=1_000)


class LongTermMemoryUpdate(BaseModel):
    category: MemoryCategory | None = None
    key: str | None = Field(default=None, min_length=1, max_length=80)
    value: str | None = Field(default=None, min_length=1, max_length=1_000)


class WorkingMemoryItem(BaseModel):
    """A session-scoped key-value record describing the current task."""

    id: str
    scope: Literal["working"] = "working"
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=1_000)
    created_at: datetime
    updated_at: datetime


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


class MemoryEvent(BaseModel):
    id: str
    scope: MemoryScope
    action: Literal[
        "saved",
        "created",
        "updated",
        "deleted",
        "cleared",
        "proposed",
        "approved",
        "rejected",
        "error",
    ]
    key: str | None = None
    value: str | None = None
    candidate_id: str | None = None
    message: str | None = None
    provider: str | None = None
    model: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    trace: ProviderTrace | None = None


class PendingMemorySuggestion(BaseModel):
    id: str
    candidate: MemoryCandidate
    created_at: datetime
