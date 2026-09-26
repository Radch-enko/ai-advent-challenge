from __future__ import annotations

from enum import StrEnum


class TaskPlanStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
