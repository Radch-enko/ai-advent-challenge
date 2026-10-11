from pydantic import BaseModel, ConfigDict


class DailyJournalNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    content: str
    revision: str | None = None
    exists: bool
    changed: bool = False
