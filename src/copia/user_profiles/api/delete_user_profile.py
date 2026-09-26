from collections.abc import Awaitable, Callable

from fastapi.concurrency import run_in_threadpool

from copia.sessions.data.sessions_repository import SessionsRepository
from copia.user_profiles.api.errors import user_profile_error
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository


def make_delete_user_profile(
    get_repository: Callable[[], JsonUserProfilesRepository],
    get_sessions: Callable[[], SessionsRepository],
) -> Callable[[str], Awaitable[None]]:
    async def delete_user_profile(profile_id: str) -> None:
        def delete() -> None:
            if get_repository().get(profile_id) is None:
                raise user_profile_error(
                    "user_profile_not_found", "User profile was not found", 404
                )
            sessions = get_sessions()
            if any(
                (session := sessions.load(summary.id)) is not None
                and session.user_profile_id == profile_id
                for summary in sessions.list()
            ):
                raise user_profile_error(
                    "user_profile_in_use", "User profile is used by a session", 409
                )
            get_repository().delete(profile_id)

        try:
            await run_in_threadpool(delete)
        except UserProfileStorageError as error:
            raise user_profile_error(
                "user_profile_unavailable", "User profiles are unavailable", 500
            ) from error

    return delete_user_profile
