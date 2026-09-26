from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class McpAccessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    enabled_tools: list[str] = Field(default_factory=list)

    @field_validator("enabled_tools")
    @classmethod
    def unique_tools(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("Enabled tool names must not be blank")
        if len(set(value)) != len(value):
            raise ValueError("Enabled tool names must be unique")
        return value
