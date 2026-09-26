from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool

from copia.user_profiles.api.errors import user_profile_error
from copia.user_profiles.data.user_profile_name_conflict_error import UserProfileNameConflictError
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository
from copia.user_profiles.domain.models.user_profile import UserProfile
from copia.user_profiles.domain.models.user_profile_update import UserProfileUpdate


def make_update_user_profile(
    get_repository: Callable[[], JsonUserProfilesRepository],
) -> Callable[[str, UserProfileUpdate], Awaitable[UserProfile]]:
    async def update_user_profile(profile_id: str, request: UserProfileUpdate) -> UserProfile:
        def update() -> UserProfile:
            current = get_repository().get(profile_id)
            if current is None:
                raise user_profile_error(
                    "user_profile_not_found", "User profile was not found", 404
                )
            changes = request.model_dump(exclude_none=True)
            changes["updated_at"] = datetime.now(UTC)
            return get_repository().update(profile_id, changes)

        try:
            return await run_in_threadpool(update)
        except UserProfileNameConflictError as error:
            raise user_profile_error(
                "user_profile_name_conflict", "A user profile with this name already exists", 409
            ) from error
        except UserProfileStorageError as error:
            raise user_profile_error(
                "user_profile_unavailable", "User profiles are unavailable", 500
            ) from error

    return update_user_profile
