from typing import Literal

from pydantic import BaseModel, Field

from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.session_memory.domain.models.memory_scope import MemoryScope


class MemoryEvent(BaseModel):
    id: str
    scope: MemoryScope
    action: Literal[
        "saved",
        "created",
        "updated",
        "deleted",
        "cleared",
        "proposed",
        "approved",
        "rejected",
        "error",
    ]
    key: str | None = None
    value: str | None = None
    candidate_id: str | None = None
    message: str | None = None
    provider: str | None = None
    model: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    trace: ProviderTrace | None = None
