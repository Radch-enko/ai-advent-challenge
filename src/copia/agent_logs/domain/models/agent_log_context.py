from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from copia.providers.domain.models.provider_name import ProviderName


class AgentLogContext(BaseModel):
    """Correlation data carried through one agent execution."""

    model_config = ConfigDict(frozen=True)

    agent_turn_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    operation: str = Field(default="primary", min_length=1, max_length=64)
    provider: ProviderName | None = None
    model: str | None = None
