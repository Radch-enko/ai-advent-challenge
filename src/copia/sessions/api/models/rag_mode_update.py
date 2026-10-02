from pydantic import BaseModel

from copia.common.domain.models.rag_settings import RagSettings


class RagModeUpdate(BaseModel):
    enabled: bool
    settings: RagSettings | None = None
