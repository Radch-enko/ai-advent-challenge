import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool

from copia.user_profiles.api.errors import user_profile_error
from copia.user_profiles.data.user_profile_name_conflict_error import UserProfileNameConflictError
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository
from copia.user_profiles.domain.models.user_profile import UserProfile
from copia.user_profiles.domain.models.user_profile_create import UserProfileCreate


def make_create_user_profile(
    get_repository: Callable[[], JsonUserProfilesRepository],
) -> Callable[[UserProfileCreate], Awaitable[UserProfile]]:
    async def create_user_profile(request: UserProfileCreate) -> UserProfile:
        def create() -> UserProfile:
            now = datetime.now(UTC)
            return get_repository().create(
                UserProfile(
                    id=str(uuid.uuid4()), **request.model_dump(), created_at=now, updated_at=now
                )
            )

        try:
            return await run_in_threadpool(create)
        except UserProfileNameConflictError as error:
            raise user_profile_error(
                "user_profile_name_conflict", "A user profile with this name already exists", 409
            ) from error
        except UserProfileStorageError as error:
            raise user_profile_error(
                "user_profile_unavailable", "User profiles are unavailable", 500
            ) from error

    return create_user_profile
