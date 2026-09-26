from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCheckpoint(BaseModel):
    id: str
    source_branch_id: str
    message_count: int = Field(ge=0)
    created_at: datetime
