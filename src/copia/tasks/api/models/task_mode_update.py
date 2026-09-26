from __future__ import annotations

from pydantic import BaseModel


class TaskModeUpdate(BaseModel):
    enabled: bool
