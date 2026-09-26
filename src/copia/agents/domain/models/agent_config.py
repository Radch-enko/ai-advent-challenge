from __future__ import annotations

from pydantic import Field, field_validator

from copia.mcp.domain.models.mcp_access_config import McpAccessConfig
from copia.providers.domain.models.llm_config import LLMConfig
from copia.sessions.domain.models.context_management_config import ContextManagementConfig


class AgentConfig(LLMConfig):
    name: str = Field(min_length=1)
    description: str | None = None
    avatar_path: str | None = None
    context_management: ContextManagementConfig = Field(default_factory=ContextManagementConfig)
    mcp_access: list[McpAccessConfig] = Field(default_factory=list)

    @field_validator("mcp_access")
    @classmethod
    def unique_connections(cls, value: list[McpAccessConfig]) -> list[McpAccessConfig]:
        ids = [item.connection_id for item in value]
        if len(set(ids)) != len(ids):
            raise ValueError("MCP connection references must be unique")
        return value
