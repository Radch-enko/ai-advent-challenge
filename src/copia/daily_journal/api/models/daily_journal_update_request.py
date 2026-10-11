from pydantic import BaseModel, ConfigDict, Field

from copia.daily_journal.api.models.daily_journal_change_request import (
    DailyJournalChangeRequest,
)


class DailyJournalUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    changes: list[DailyJournalChangeRequest] = Field(min_length=1, max_length=50)
