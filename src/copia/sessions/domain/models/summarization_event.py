from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.provider_trace import ProviderTrace


class SummarizationEvent(BaseModel):
    id: str
    status: Literal["completed", "failed"]
    after_message_index: int = Field(ge=0)
    start_message_index: int = Field(ge=0)
    message_count: int = Field(gt=0)
    provider: ProviderName
    model: str
    duration_seconds: float = Field(ge=0)
    usage: dict[str, int] | None = None
    trace: ProviderTrace | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
