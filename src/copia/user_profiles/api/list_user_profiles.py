from collections.abc import Awaitable, Callable

from fastapi.concurrency import run_in_threadpool

from copia.user_profiles.api.errors import user_profile_error
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository
from copia.user_profiles.domain.models.user_profile import UserProfile


def make_list_user_profiles(
    get_repository: Callable[[], JsonUserProfilesRepository],
) -> Callable[[], Awaitable[list[UserProfile]]]:
    def sorted_user_profiles() -> list[UserProfile]:
        return sorted(
            get_repository().list(), key=lambda profile: (profile.name.casefold(), profile.id)
        )

    async def list_user_profiles() -> list[UserProfile]:
        try:
            return await run_in_threadpool(sorted_user_profiles)
        except UserProfileStorageError as error:
            raise user_profile_error(
                "user_profile_unavailable", "User profiles are unavailable", 500
            ) from error

    return list_user_profiles
