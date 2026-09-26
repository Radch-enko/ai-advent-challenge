from __future__ import annotations

from pydantic import BaseModel

from copia.agents.domain.models.agent_config import AgentConfig


class CreateAgentResponse(BaseModel):
    agent_id: str
    config: AgentConfig
    long_term_memory_enabled: bool
