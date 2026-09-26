from datetime import datetime

from pydantic import BaseModel, Field


class ConversationBranch(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    created_at: datetime
