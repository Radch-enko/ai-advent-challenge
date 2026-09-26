from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class Invariant(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=400)
    created_at: datetime
    updated_at: datetime

    @field_validator("name", "text", mode="before")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value
