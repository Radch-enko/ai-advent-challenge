from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import HTTPException, status

from copia.profile_memory.api.errors import memory_storage_error
from copia.profile_memory.api.threadpool import ThreadpoolRunner
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.profile_memory.domain.models.long_term_memory_update import LongTermMemoryUpdate


def make_update_profile_memory(
    get_repository: Callable[[], ProfileMemoryRepository],
    require_profile: Callable[[str], Awaitable[None]],
    get_threadpool: Callable[[], ThreadpoolRunner],
) -> Callable[[str, str, LongTermMemoryUpdate], Awaitable[LongTermMemoryItem]]:
    async def update_profile_memory(
        profile_name: str, item_id: str, request: LongTermMemoryUpdate
    ) -> LongTermMemoryItem:
        await require_profile(profile_name)
        try:
            changes = request.model_dump(exclude_none=True)
            changes["updated_at"] = datetime.now(UTC)
            return await get_threadpool()(get_repository().update, profile_name, item_id, changes)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown memory item"
            ) from error
        except (OSError, ValueError) as error:
            raise memory_storage_error() from error

    return update_profile_memory
