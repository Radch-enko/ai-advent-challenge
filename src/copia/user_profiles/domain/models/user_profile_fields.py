from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from copia.user_profiles.domain.models.profile_types import (
    Language,
    ResponseFormat,
    Tone,
    Verbosity,
)
from copia.user_profiles.domain.services.profile_preferences import profile_preferences_block_size


class _UserProfileFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    language: Language
    tone: Tone
    verbosity: Verbosity
    response_format: list[ResponseFormat] = Field(min_length=1, max_length=3)
    constraints: list[str] = Field(default_factory=list, max_length=8)

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
        normalized = []
        for constraint in value:
            constraint = constraint.strip()
            if not 1 <= len(constraint) <= 200:
                raise ValueError("constraints must contain 1 to 200 characters")
            normalized.append(constraint)
        if sum(map(len, normalized)) > 1200:
            raise ValueError("constraints must not exceed 1200 characters in total")
        return normalized

    @model_validator(mode="after")
    def validate_rendered_block_size(self) -> _UserProfileFields:
        if profile_preferences_block_size(self) > 3_000:
            raise ValueError("rendered user profile preferences exceed 3000 characters")
        return self
