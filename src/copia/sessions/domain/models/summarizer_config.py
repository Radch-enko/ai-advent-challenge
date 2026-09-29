from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from copia.common.domain.services.prompt_resources import load_prompt
from copia.providers.domain.models.generation_config import GenerationConfig
from copia.providers.domain.models.provider_name import ProviderName

DEFAULT_SUMMARIZATION_PROMPT = load_prompt("copia.sessions", "summarizer.md")


class SummarizerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName | None = None
    model: str | None = Field(default=None, min_length=1)
    prompt: str = Field(default=DEFAULT_SUMMARIZATION_PROMPT, min_length=1)
    generation: GenerationConfig = Field(
        default_factory=lambda: GenerationConfig(
            max_output_tokens=512,
            temperature=0.2,
            top_p=1.0,
        )
    )
