from pydantic import BaseModel, Field


class McpServerSummary(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=100)
