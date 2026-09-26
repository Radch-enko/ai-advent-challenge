from pydantic import BaseModel, Field

from copia.profile_memory.domain.models.memory_category import MemoryCategory


class LongTermMemoryUpdate(BaseModel):
    category: MemoryCategory | None = None
    key: str | None = Field(default=None, min_length=1, max_length=80)
    value: str | None = Field(default=None, min_length=1, max_length=1_000)
