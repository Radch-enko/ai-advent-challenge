from pydantic import BaseModel, Field

from copia.agents.domain.models.agent_config import AgentConfig


class MessageRequest(BaseModel):
    content: str = Field(min_length=1)
    config: AgentConfig | None = None
