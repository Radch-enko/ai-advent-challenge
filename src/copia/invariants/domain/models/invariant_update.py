from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class InvariantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    text: str | None = Field(default=None, min_length=1, max_length=400)

    @field_validator("name", "text", mode="before")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value
