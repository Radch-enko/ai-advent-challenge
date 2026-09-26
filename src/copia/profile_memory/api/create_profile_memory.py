import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import HTTPException, status

from copia.profile_memory.api.errors import memory_storage_error
from copia.profile_memory.api.threadpool import ThreadpoolRunner
from copia.profile_memory.data.profile_memory_limit_exceeded import ProfileMemoryLimitExceeded
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.profile_memory.domain.models.long_term_memory_create import LongTermMemoryCreate
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem


def make_create_profile_memory(
    get_repository: Callable[[], ProfileMemoryRepository],
    require_profile: Callable[[str], Awaitable[None]],
    get_threadpool: Callable[[], ThreadpoolRunner],
) -> Callable[[str, LongTermMemoryCreate], Awaitable[LongTermMemoryItem]]:
    def create(profile_name: str, request: LongTermMemoryCreate) -> LongTermMemoryItem:
        now = datetime.now(UTC)
        item = LongTermMemoryItem(
            id=str(uuid.uuid4()), **request.model_dump(), created_at=now, updated_at=now
        )
        return get_repository().create(profile_name, item)

    async def create_profile_memory(
        profile_name: str, request: LongTermMemoryCreate
    ) -> LongTermMemoryItem:
        await require_profile(profile_name)
        try:
            return await get_threadpool()(create, profile_name, request)
        except ProfileMemoryLimitExceeded as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Profile memory limit reached"
            ) from error
        except (OSError, ValueError) as error:
            raise memory_storage_error() from error

    return create_profile_memory
