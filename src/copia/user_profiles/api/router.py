from collections.abc import Callable

from fastapi import APIRouter, status

from copia.sessions.data.sessions_repository import SessionsRepository
from copia.user_profiles.api.create_user_profile import make_create_user_profile
from copia.user_profiles.api.delete_user_profile import make_delete_user_profile
from copia.user_profiles.api.list_user_profiles import make_list_user_profiles
from copia.user_profiles.api.update_user_profile import make_update_user_profile
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository
from copia.user_profiles.domain.models.user_profile import UserProfile


def create_user_profiles_router(
    get_repository: Callable[[], JsonUserProfilesRepository],
    get_sessions: Callable[[], SessionsRepository],
) -> APIRouter:
    router = APIRouter()
    router.add_api_route(
        "/user-profiles",
        make_list_user_profiles(get_repository),
        methods=["GET"],
        response_model=list[UserProfile],
    )
    router.add_api_route(
        "/user-profiles",
        make_create_user_profile(get_repository),
        methods=["POST"],
        response_model=UserProfile,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        "/user-profiles/{profile_id}",
        make_update_user_profile(get_repository),
        methods=["PATCH"],
        response_model=UserProfile,
    )
    router.add_api_route(
        "/user-profiles/{profile_id}",
        make_delete_user_profile(get_repository, get_sessions),
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
    )
    return router
