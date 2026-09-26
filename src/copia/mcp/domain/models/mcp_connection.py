from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from copia.mcp.domain.models.mcp_server_summary import McpServerSummary
from copia.mcp.domain.models.mcp_tool_summary import McpToolSummary


class McpConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    endpoint: str = Field(min_length=1, max_length=2048)
    header_name: str | None = Field(default=None, max_length=256)
    header_value_env: str | None = Field(default=None, pattern=r"^COPIA_MCP_[A-Z0-9_]+$")
    server: McpServerSummary | None = None
    tools: list[McpToolSummary] = Field(default_factory=list)
    updated_at: datetime

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Connection name must not be blank")
        return value

    @model_validator(mode="after")
    def validate_header_pair(self) -> McpConnection:
        if (self.header_name is None) != (self.header_value_env is None):
            raise ValueError("header_name and header_value_env must be provided together")
        return self
