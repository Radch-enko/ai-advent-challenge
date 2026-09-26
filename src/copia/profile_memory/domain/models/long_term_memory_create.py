from pydantic import BaseModel, Field

from copia.profile_memory.domain.models.memory_category import MemoryCategory


class LongTermMemoryCreate(BaseModel):
    category: MemoryCategory
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=1_000)
