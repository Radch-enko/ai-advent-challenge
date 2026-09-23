from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class McpToolSummary(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    input_schema: dict[str, Any] = Field(default_factory=dict)


class McpServerSummary(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=100)


class McpDiscoveryResult(BaseModel):
    server: McpServerSummary
    endpoint: str = Field(min_length=1, max_length=2048)
    tools: list[McpToolSummary] = Field(default_factory=list)


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


class McpToolDefinition(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)


class McpToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class McpToolResult(BaseModel):
    call_id: str
    name: str
    content: str
    is_error: bool = False


class McpCallResult(BaseModel):
    content: list[dict[str, Any]] = Field(default_factory=list)
    structured_content: dict[str, Any] | None = None
    is_error: bool = False


class McpApproval(BaseModel):
    id: str
    connection_id: str
    connection_name: str
    tool_name: str
    arguments: dict[str, Any]
    decision: Literal["pending", "approved", "rejected"] = "pending"
