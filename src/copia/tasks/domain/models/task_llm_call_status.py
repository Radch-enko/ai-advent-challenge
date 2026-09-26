from __future__ import annotations

from enum import StrEnum


class TaskLlmCallStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
