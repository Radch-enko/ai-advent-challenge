from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DailyJournalSection(StrEnum):
    MAIN = "main"
    NOTES = "notes"
    IDEAS = "ideas"
    NEXT_STEPS = "next_steps"
    GRATITUDE = "gratitude"


class DailyJournalOperation(StrEnum):
    ADD = "add"
    REPLACE = "replace"
    REMOVE = "remove"
    COMPLETE_TASK = "complete_task"


class DailyJournalChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: DailyJournalOperation
    section: DailyJournalSection
    text: str = Field(min_length=1, max_length=2000)
    previous_text: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("text", "previous_text")
    @classmethod
    def validate_single_line(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or "\n" in normalized or "\r" in normalized:
            raise ValueError("Daily journal entries must be non-empty single lines")
        return normalized

    @model_validator(mode="after")
    def validate_previous_text(self) -> DailyJournalChange:
        needs_previous = self.operation in {
            DailyJournalOperation.REPLACE,
            DailyJournalOperation.REMOVE,
        }
        if needs_previous != (self.previous_text is not None):
            raise ValueError("previous_text is required only for replace and remove operations")
        if self.operation == DailyJournalOperation.COMPLETE_TASK and (
            self.section != DailyJournalSection.NEXT_STEPS
        ):
            raise ValueError("Only next-step entries can be completed")
        return self
