from pydantic import BaseModel, ConfigDict, Field

from copia.daily_journal.domain.models.daily_journal_change import DailyJournalChange


class DailyJournalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    changes: list[DailyJournalChange] = Field(min_length=1, max_length=50)
