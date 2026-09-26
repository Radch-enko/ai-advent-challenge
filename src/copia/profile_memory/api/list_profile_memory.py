from collections.abc import Awaitable, Callable

from copia.profile_memory.api.errors import memory_storage_error
from copia.profile_memory.api.threadpool import ThreadpoolRunner
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem


def make_list_profile_memory(
    get_repository: Callable[[], ProfileMemoryRepository],
    require_profile: Callable[[str], Awaitable[None]],
    get_threadpool: Callable[[], ThreadpoolRunner],
) -> Callable[[str], Awaitable[list[LongTermMemoryItem]]]:
    async def list_profile_memory(profile_name: str) -> list[LongTermMemoryItem]:
        await require_profile(profile_name)
        try:
            return await get_threadpool()(get_repository().load, profile_name)
        except (OSError, ValueError) as error:
            raise memory_storage_error() from error

    return list_profile_memory
