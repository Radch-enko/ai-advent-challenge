from __future__ import annotations

from pydantic import BaseModel, Field

from copia.sessions.domain.models.context_strategy_name import ContextStrategyName


class ContextManagementUpdate(BaseModel):
    enabled: bool | None = None
    strategy: ContextStrategyName | None = None
    recent_message_limit: int | None = Field(default=None, ge=1)
