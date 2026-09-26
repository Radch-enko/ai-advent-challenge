from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from copia.user_profiles.domain.models.profile_types import (
    Language,
    ResponseFormat,
    Tone,
    Verbosity,
)
from copia.user_profiles.domain.models.user_profile_fields import _UserProfileFields


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    language: Language | None = None
    tone: Tone | None = None
    verbosity: Verbosity | None = None
    response_format: list[ResponseFormat] | None = Field(default=None, min_length=1, max_length=3)
    constraints: list[str] | None = Field(default=None, max_length=8)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("response_format")
    @classmethod
    def unique_response_formats(cls, value: list[ResponseFormat]) -> list[ResponseFormat]:
        if len(set(value)) != len(value):
            raise ValueError("response_format values must be unique")
        return value

    @field_validator("constraints")
    @classmethod
    def normalize_constraints(cls, value: list[str]) -> list[str]:
        normalized = [constraint.strip() for constraint in value]
        if any(not 1 <= len(item) <= 200 for item in normalized):
            raise ValueError("constraints must contain 1 to 200 characters")
        if sum(map(len, normalized)) > 1200:
            raise ValueError("constraints must not exceed 1200 characters in total")
        return normalized

    @model_validator(mode="after")
    def validate_changed_fields(self) -> UserProfileUpdate:
        values = self.model_dump(exclude_none=True)
        _UserProfileFields.model_validate(
            {
                "name": values.get("name", "Valid name"),
                "language": values.get("language", "auto"),
                "tone": values.get("tone", "neutral"),
                "verbosity": values.get("verbosity", "balanced"),
                "response_format": values.get("response_format", ["plain_text"]),
                "constraints": values.get("constraints", []),
            }
        )
        return self
