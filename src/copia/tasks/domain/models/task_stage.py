from __future__ import annotations

from enum import StrEnum


class TaskStage(StrEnum):
    PLANNING = "planning"
    PLAN_REVIEW = "plan_review"
    EXECUTION = "execution"
    VALIDATION = "validation"
    REPORT = "report"
    DONE = "done"
