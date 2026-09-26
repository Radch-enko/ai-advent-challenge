from pydantic import BaseModel, Field


class ForkSessionRequest(BaseModel):
    message_index: int = Field(ge=0)
