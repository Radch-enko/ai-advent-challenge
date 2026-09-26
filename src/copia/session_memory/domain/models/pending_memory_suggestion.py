from datetime import datetime

from pydantic import BaseModel

from copia.session_memory.domain.models.memory_candidate import MemoryCandidate


class PendingMemorySuggestion(BaseModel):
    id: str
    candidate: MemoryCandidate
    created_at: datetime
