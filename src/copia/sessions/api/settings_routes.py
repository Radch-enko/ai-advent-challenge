import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status

from copia.sessions.api.models.context_management_update import ContextManagementUpdate
from copia.sessions.api.models.fork_session_request import ForkSessionRequest
from copia.sessions.api.models.long_term_memory_toggle_update import LongTermMemoryToggleUpdate
from copia.sessions.api.models.user_profile_selection_update import UserProfileSelectionUpdate
from copia.sessions.api.threadpool import ThreadpoolRunner
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.models.context_strategy_name import ContextStrategyName
from copia.user_profiles.api.errors import user_profile_error
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository


class SessionSettingsRoutes:
    def __init__(
        self,
        get_repository: Callable[[], SessionsRepository],
        get_user_profiles: Callable[[], JsonUserProfilesRepository],
        require_session: Callable[[str], Awaitable[ChatSession]],
        get_session_locked: Callable[[str], ChatSession],
        mutation_lock: Callable[[str], AbstractContextManager[Any]],
        get_lifecycle_lock: Callable[[], AbstractContextManager[Any]],
        get_threadpool: Callable[[], ThreadpoolRunner],
    ) -> None:
        self._get_repository = get_repository
        self._get_user_profiles = get_user_profiles
        self._require_session = require_session
        self._get_session_locked = get_session_locked
        self._mutation_lock = mutation_lock
        self._get_lifecycle_lock = get_lifecycle_lock
        self._get_threadpool = get_threadpool

    async def get_session_facts(self, session_id: str) -> dict[str, str]:
        await self._require_session(session_id)
        try:
            return await self._get_threadpool()(self._get_repository().load_facts, session_id)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session facts are unavailable",
            ) from error

    def update_session_context_management(
        self, session_id: str, request: ContextManagementUpdate
    ) -> ChatSession:
        with self._mutation_lock(session_id):
            session = self._get_session_locked(session_id)
            if request.enabled is not None:
                session.config.context_management.enabled = request.enabled
            if request.strategy is not None:
                session.config.context_management.strategy = request.strategy
            if request.recent_message_limit is not None:
                session.config.context_management.recent_message_limit = (
                    request.recent_message_limit
                )
            session.updated_at = datetime.now(UTC)
            self._get_repository().save(session)
            return session

    async def update_session_user_profile(
        self, session_id: str, request: UserProfileSelectionUpdate
    ) -> ChatSession:
        def update() -> ChatSession:
            with self._mutation_lock(session_id):
                session = self._get_session_locked(session_id)
                if (
                    request.user_profile_id is not None
                    and self._get_user_profiles().get(request.user_profile_id) is None
                ):
                    raise user_profile_error(
                        "user_profile_not_found", "User profile was not found", 404
                    )
                session.user_profile_id = request.user_profile_id
                session.updated_at = datetime.now(UTC)
                self._get_repository().save(session)
                return session

        try:
            return await self._get_threadpool()(update)
        except UserProfileStorageError as error:
            raise user_profile_error(
                "user_profile_unavailable", "User profiles are unavailable", 500
            ) from error

    async def update_session_long_term_memory(
        self, session_id: str, request: LongTermMemoryToggleUpdate
    ) -> ChatSession:
        return await self._get_threadpool()(
            self._update_session_long_term_memory, session_id, request
        )

    def _update_session_long_term_memory(
        self, session_id: str, request: LongTermMemoryToggleUpdate
    ) -> ChatSession:
        with self._mutation_lock(session_id):
            session = self._get_session_locked(session_id)
            if session.profile_name is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Long-term memory is unavailable without a profile",
                )
            session.long_term_memory_enabled = request.enabled
            session.updated_at = datetime.now(UTC)
            self._get_repository().save(session)
            return session

    def fork_session(self, session_id: str, request: ForkSessionRequest) -> ChatSession:
        with self._get_lifecycle_lock():
            source = self._get_session_locked(session_id)
            if source.config.context_management.strategy != ContextStrategyName.BRANCHING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Forking requires the branching strategy",
                )
            if request.message_index >= len(source.messages):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Message index is outside the transcript",
                )
            now = datetime.now(UTC)
            fork = ChatSession(
                id=str(uuid.uuid4()),
                config=source.config.model_copy(deep=True),
                messages=[
                    message.model_copy(update={"agent_log_id": None})
                    for message in source.messages[: request.message_index + 1]
                ],
                title=f"{source.title or 'Новый чат'} · ветка",
                profile_name=source.profile_name,
                user_profile_id=source.user_profile_id,
                long_term_memory_enabled=source.long_term_memory_enabled,
                task_mode_enabled=source.task_mode_enabled,
                created_at=now,
                updated_at=now,
            )
            self._get_repository().save(fork)
            return fork

    def facts_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/facts",
            self.get_session_facts,
            methods=["GET"],
            response_model=dict[str, str],
        )
        return router

    def settings_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/context-management",
            self.update_session_context_management,
            methods=["PATCH"],
            response_model=ChatSession,
        )
        router.add_api_route(
            "/sessions/{session_id}/user-profile",
            self.update_session_user_profile,
            methods=["PATCH"],
            response_model=ChatSession,
        )
        router.add_api_route(
            "/sessions/{session_id}/long-term-memory",
            self.update_session_long_term_memory,
            methods=["PATCH"],
            response_model=ChatSession,
        )
        router.add_api_route(
            "/sessions/{session_id}/fork",
            self.fork_session,
            methods=["POST"],
            response_model=ChatSession,
            status_code=status.HTTP_201_CREATED,
        )
        return router
