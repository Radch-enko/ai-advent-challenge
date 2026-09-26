from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StructuredOutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    json_schema: dict[str, Any] = Field(alias="schema", serialization_alias="schema")
    strict: bool = True
