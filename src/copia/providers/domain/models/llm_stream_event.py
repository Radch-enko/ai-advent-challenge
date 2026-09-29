from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from copia.providers.domain.models.llm_response import LLMResponse


class LLMStreamEvent(BaseModel):
    kind: Literal["text_delta", "completed"]
    text: str | None = None
    response: LLMResponse | None = None
