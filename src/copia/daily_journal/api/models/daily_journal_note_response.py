from pydantic import BaseModel, ConfigDict


class DailyJournalNoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    content: str
    revision: str | None
    exists: bool
    changed: bool = False
