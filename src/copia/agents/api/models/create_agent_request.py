from __future__ import annotations

from pydantic import BaseModel, model_validator

from copia.agents.domain.models.agent_config import AgentConfig
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class CreateAgentRequest(BaseModel):
    profile_name: str | None = None
    config: AgentConfig | None = None
    long_term_memory_enabled: bool = False

    @model_validator(mode="after")
    def require_one_source(self) -> CreateAgentRequest:
        if self.profile_name is not None:
            validate_path_identifier(self.profile_name, "profile name")
        if (self.profile_name is None) == (self.config is None):
            raise ValueError("Provide exactly one of profile_name or config")
        if self.long_term_memory_enabled and self.profile_name is None:
            raise ValueError("Long-term memory is available only for profile agents")
        return self
