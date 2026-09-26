import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.agent_logs.domain.models.agent_log_operation import AgentLogOperation
from copia.security.domain.services.credential_sanitizer import sanitize_text
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.services.context_strategy import _render_user_profile_block
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository
from copia.user_profiles.domain.models.user_profile import UserProfile


class TurnProfileLoader:
    def __init__(
        self,
        get_profiles: Callable[[], JsonUserProfilesRepository],
        get_agent_logs: Callable[[], AgentLogStore],
        get_threadpool: Callable[[], Callable[..., Awaitable[Any]]],
        get_initialization_error: Callable[[], Callable[..., HTTPException]],
    ) -> None:
        self._get_profiles = get_profiles
        self._get_agent_logs = get_agent_logs
        self._get_threadpool = get_threadpool
        self._get_initialization_error = get_initialization_error

    async def load(self, session: ChatSession, agent_log_id: str) -> UserProfile | None:
        started = time.perf_counter()
        if session.user_profile_id is None:
            self._get_agent_logs().append_operation(
                AgentLogOperation(
                    id=str(uuid.uuid4()),
                    agent_turn_id=agent_log_id,
                    session_id=session.id,
                    operation="user_profile_load",
                    status="skipped",
                    preference_count=0,
                    applied=False,
                    duration_seconds=time.perf_counter() - started,
                    created_at=datetime.now(UTC),
                )
            )
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
            self._get_agent_logs().append_operation(
                AgentLogOperation(
                    id=str(uuid.uuid4()),
                    agent_turn_id=agent_log_id,
                    session_id=session.id,
                    operation="user_profile_load",
                    status="failed",
                    profile_id=session.user_profile_id,
                    preference_count=0,
                    applied=False,
                    duration_seconds=time.perf_counter() - started,
                    error_code="user_profile_unavailable",
                    message="User profile could not be loaded",
                    created_at=datetime.now(UTC),
                )
            )
            raise self._get_initialization_error()(
                agent_log_id, "User profile is unavailable", "user_profile_unavailable", 409
            ) from error
        self._get_agent_logs().append_operation(
            AgentLogOperation(
                id=str(uuid.uuid4()),
                agent_turn_id=agent_log_id,
                session_id=session.id,
                operation="user_profile_load",
                status="completed",
                profile_id=profile.id,
                profile_name=sanitize_text(profile.name),
                preference_count=5,
                applied=True,
                duration_seconds=time.perf_counter() - started,
                created_at=datetime.now(UTC),
            )
        )
        return profile
