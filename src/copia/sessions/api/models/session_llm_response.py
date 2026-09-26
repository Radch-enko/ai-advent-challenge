from __future__ import annotations

from pydantic import BaseModel

from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName


class SessionLLMResponse(BaseModel):
    """Session response data without the legacy synthetic provider trace."""

    content: str
    provider: ProviderName
    model: str
    usage: dict[str, int] | None = None
    context_window: int | None = None
    structured_data: dict[str, object] | list[object] | None = None
    # Сохраняем форму ответа без сериализации данных провайдера.
    trace: None = None

    @classmethod
    def from_response(cls, response: LLMResponse) -> SessionLLMResponse:
        return cls(
            content=response.content,
            provider=response.provider,
            model=response.model,
            usage=response.usage,
            context_window=response.context_window,
            structured_data=response.structured_data,
        )
