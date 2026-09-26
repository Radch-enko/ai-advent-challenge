from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TaskValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    issues: list[str]
    checked_step_ids: list[str]
    checked_invariant_ids: list[str] = Field(default_factory=list)
    invariant_issues: list[str] = Field(default_factory=list)
