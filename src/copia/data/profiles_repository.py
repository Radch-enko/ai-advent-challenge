from __future__ import annotations

import json
from pathlib import Path

from ..domain.models.config import AgentConfig


class ProfilesRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict[str, AgentConfig]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        return {name: AgentConfig.model_validate(config) for name, config in raw.items()}
