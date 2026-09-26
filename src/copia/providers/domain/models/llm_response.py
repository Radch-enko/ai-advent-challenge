from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.providers.domain.models.tool_call import ToolCall


class LLMResponse(BaseModel):
    content: str
    provider: ProviderName
    model: str
    usage: dict[str, int] | None = None
    context_window: int | None = Field(default=None, gt=0)
    structured_data: dict[str, Any] | list[Any] | None = None
    trace: ProviderTrace | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
