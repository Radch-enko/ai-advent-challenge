from datetime import datetime

from pydantic import BaseModel


class ChatSessionSummary(BaseModel):
    id: str
    title: str | None = None
    profile_name: str | None = None
    updated_at: datetime
