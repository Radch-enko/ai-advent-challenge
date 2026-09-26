from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScheduledJobStatusResponse(BaseModel):
    id: str
    name: str
    status: Literal["wait", "progress", "completed"]
    next_run_at: datetime | None
