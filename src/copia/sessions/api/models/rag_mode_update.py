from pydantic import BaseModel


class RagModeUpdate(BaseModel):
    enabled: bool
