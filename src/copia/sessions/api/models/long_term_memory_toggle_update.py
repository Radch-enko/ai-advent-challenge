from __future__ import annotations

from pydantic import BaseModel


class LongTermMemoryToggleUpdate(BaseModel):
    enabled: bool
