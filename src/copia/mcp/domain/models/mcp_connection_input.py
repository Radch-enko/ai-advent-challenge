from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class McpConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    endpoint: str = Field(min_length=1, max_length=2048)
    header_name: str | None = Field(default=None, max_length=256)
    header_value_env: str | None = Field(default=None, pattern=r"^COPIA_MCP_[A-Z0-9_]+$")

    @model_validator(mode="after")
    def validate_header_pair(self) -> McpConnectionInput:
        if (self.header_name is None) != (self.header_value_env is None):
            raise ValueError("header_name and header_value_env must be provided together")
        return self
