from __future__ import annotations

from pydantic import BaseModel, Field


class McpToolSummary(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class McpServerSummary(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=100)


class McpDiscoveryResult(BaseModel):
    server: McpServerSummary
    endpoint: str = Field(min_length=1, max_length=2048)
    tools: list[McpToolSummary] = Field(default_factory=list)
