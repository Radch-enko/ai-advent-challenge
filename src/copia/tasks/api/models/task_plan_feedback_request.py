from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TaskPlanFeedbackRequest(BaseModel):
    feedback: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_non_blank_feedback(self) -> TaskPlanFeedbackRequest:
        if not self.feedback.strip():
            raise ValueError("Plan change feedback cannot be blank")
        self.feedback = self.feedback.strip()
        return self
