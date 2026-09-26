from collections.abc import Callable

from fastapi import APIRouter, status

from copia.agents.domain.models.agent_config import AgentConfig
from copia.profile_memory.api.create_profile_memory import make_create_profile_memory
from copia.profile_memory.api.delete_profile_memory import make_delete_profile_memory
from copia.profile_memory.api.list_profile_memory import make_list_profile_memory
from copia.profile_memory.api.require_profile import make_require_profile
from copia.profile_memory.api.threadpool import ThreadpoolRunner
from copia.profile_memory.api.update_profile_memory import make_update_profile_memory
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem


def create_profile_memory_router(
    get_repository: Callable[[], ProfileMemoryRepository],
    get_profiles: Callable[[], dict[str, AgentConfig]],
    get_threadpool: Callable[[], ThreadpoolRunner],
) -> APIRouter:
    router = APIRouter()
    require_profile = make_require_profile(get_profiles, get_threadpool)
    router.add_api_route(
        "/profiles/{profile_name}/memory",
        make_list_profile_memory(get_repository, require_profile, get_threadpool),
        methods=["GET"],
        response_model=list[LongTermMemoryItem],
    )
    router.add_api_route(
        "/profiles/{profile_name}/memory",
        make_create_profile_memory(get_repository, require_profile, get_threadpool),
        methods=["POST"],
        response_model=LongTermMemoryItem,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        "/profiles/{profile_name}/memory/{item_id}",
        make_update_profile_memory(get_repository, require_profile, get_threadpool),
        methods=["PATCH"],
        response_model=LongTermMemoryItem,
    )
    router.add_api_route(
        "/profiles/{profile_name}/memory/{item_id}",
        make_delete_profile_memory(get_repository, require_profile, get_threadpool),
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
    )
    return router
