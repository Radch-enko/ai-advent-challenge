from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from copia.providers.domain.models.generation_config import GenerationConfig
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.structured_output_config import StructuredOutputConfig


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    model: str = Field(min_length=1)
    system_prompt: str | None = None
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    structured_output: StructuredOutputConfig | None = None
    provider_options: dict[str, Any] = Field(default_factory=dict)
