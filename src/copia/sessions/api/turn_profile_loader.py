from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.services.context_strategy import _render_user_profile_block
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository
from copia.user_profiles.domain.models.user_profile import UserProfile


class TurnProfileLoader:
    def __init__(
        self,
        get_profiles: Callable[[], JsonUserProfilesRepository],
        get_threadpool: Callable[[], Callable[..., Awaitable[Any]]],
        get_initialization_error: Callable[[], Callable[..., HTTPException]],
    ) -> None:
        self._get_profiles = get_profiles
        self._get_threadpool = get_threadpool
        self._get_initialization_error = get_initialization_error

    async def load(self, session: ChatSession) -> UserProfile | None:
        if session.user_profile_id is None:
            return None
        try:
            profile = await self._get_threadpool()(
                self._get_profiles().get, session.user_profile_id
            )
            if profile is None:
                raise UserProfileStorageError("User profile was not found")
            # Проверяем экранированный prompt до фиксации успешной операции в логе.
            _render_user_profile_block(profile)
        except (UserProfileStorageError, OSError, ValueError) as error:
            raise self._get_initialization_error()(
                "User profile is unavailable", "user_profile_unavailable", 409
            ) from error
        return profile
