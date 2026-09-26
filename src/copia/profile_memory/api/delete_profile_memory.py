from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from copia.profile_memory.api.errors import memory_storage_error
from copia.profile_memory.api.threadpool import ThreadpoolRunner
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository


def make_delete_profile_memory(
    get_repository: Callable[[], ProfileMemoryRepository],
    require_profile: Callable[[str], Awaitable[None]],
    get_threadpool: Callable[[], ThreadpoolRunner],
) -> Callable[[str, str], Awaitable[None]]:
    async def delete_profile_memory(profile_name: str, item_id: str) -> None:
        await require_profile(profile_name)
        try:
            await get_threadpool()(get_repository().delete_item, profile_name, item_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown memory item"
            ) from error
        except (OSError, ValueError) as error:
            raise memory_storage_error() from error

    return delete_profile_memory
