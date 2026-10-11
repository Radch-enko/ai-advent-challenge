from pydantic import BaseModel, ConfigDict, Field

from copia.daily_journal.domain.models.daily_journal_change import (
    DailyJournalOperation,
    DailyJournalSection,
)


class DailyJournalChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: DailyJournalOperation
    section: DailyJournalSection
    text: str = Field(min_length=1, max_length=2000)
    previous_text: str | None = Field(default=None, max_length=2000)
