from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class McpDiscoveryRequest(BaseModel):
    endpoint: str = Field(min_length=1)
    header_name: str | None = None
    header_value: str | None = None

    @model_validator(mode="after")
    def validate_header_pair(self) -> McpDiscoveryRequest:
        if (self.header_name is None) != (self.header_value is None):
            raise ValueError("header_name and header_value must be provided together")
        return self
