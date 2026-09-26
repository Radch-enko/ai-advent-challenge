from pydantic import BaseModel, Field

from copia.mcp.domain.models.mcp_server_summary import McpServerSummary
from copia.mcp.domain.models.mcp_tool_summary import McpToolSummary


class McpDiscoveryResult(BaseModel):
    server: McpServerSummary
    endpoint: str = Field(min_length=1, max_length=2048)
    tools: list[McpToolSummary] = Field(default_factory=list)
