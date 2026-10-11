from __future__ import annotations

import json
import re
from pathlib import Path

from copia.agents.domain.models.agent_config import AgentConfig
from copia.common.domain.services.prompt_resources import load_prompt

_PROMPT_RESOURCE_PATTERN = re.compile(r"^(copia(?:\.[a-z_]+)+):([a-z_][a-z0-9_]*\.md)$")


class ProfilesRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict[str, AgentConfig]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        profiles: dict[str, AgentConfig] = {}
        for name, raw_config in raw.items():
            config = dict(raw_config)
            resource = config.pop("system_prompt_resource", None)
            if resource is not None:
                match = _PROMPT_RESOURCE_PATTERN.fullmatch(resource)
                if match is None or "system_prompt" in config:
                    raise ValueError("Invalid system prompt resource configuration")
                config["system_prompt"] = load_prompt(match.group(1), match.group(2))
            profiles[name] = AgentConfig.model_validate(config)
        return profiles
