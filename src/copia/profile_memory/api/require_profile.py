from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from copia.agents.domain.models.agent_config import AgentConfig
from copia.profile_memory.api.errors import memory_storage_error
from copia.profile_memory.api.threadpool import ThreadpoolRunner
from copia.storage.domain.services.path_identifiers import validate_path_identifier


def make_require_profile(
    get_profiles: Callable[[], dict[str, AgentConfig]],
    get_threadpool: Callable[[], ThreadpoolRunner],
) -> Callable[[str], Awaitable[None]]:
    async def require_profile(profile_name: str) -> None:
        try:
            validate_path_identifier(profile_name, "profile name")
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid profile name") from error
        try:
            profiles = await get_threadpool()(get_profiles)
        except (OSError, ValueError) as error:
            raise memory_storage_error() from error
        if profile_name not in profiles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown profile: {profile_name}"
            )

    return require_profile
