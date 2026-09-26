from __future__ import annotations

from pydantic import BaseModel, model_validator

from copia.agents.domain.models.agent_config import AgentConfig
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class CreateSessionRequest(BaseModel):
    profile_name: str | None = None
    config: AgentConfig | None = None
    user_profile_id: str | None = None
    task_mode_enabled: bool = False

    @model_validator(mode="after")
    def require_one_source(self) -> CreateSessionRequest:
        if self.profile_name is not None:
            validate_path_identifier(self.profile_name, "profile name")
        if (self.profile_name is None) == (self.config is None):
            raise ValueError("Provide exactly one of profile_name or config")
        return self
