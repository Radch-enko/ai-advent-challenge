from __future__ import annotations

from copia.providers.domain.models.llm_config import LLMConfig


class CompletionConfig(LLMConfig):
    """Configuration for a direct, stateless LLM request."""
