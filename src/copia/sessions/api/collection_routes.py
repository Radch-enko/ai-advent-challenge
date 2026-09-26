import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from copia.agents.domain.models.agent_config import AgentConfig
from copia.sessions.api.models.create_session_request import CreateSessionRequest
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.models.chat_session_summary import ChatSessionSummary
from copia.storage.domain.services.path_identifiers import validate_path_identifier
from copia.user_profiles.api.errors import user_profile_error
from copia.user_profiles.data.user_profile_storage_error import UserProfileStorageError
from copia.user_profiles.data.user_profiles_repository import JsonUserProfilesRepository


class SessionCollectionRoutes:
    def __init__(
        self,
        get_repository: Callable[[], SessionsRepository],
        get_profiles: Callable[[], dict[str, AgentConfig]],
        get_user_profiles: Callable[[], JsonUserProfilesRepository],
        recover_tasks: Callable[[str, ChatSession], None],
    ) -> None:
        self._get_repository = get_repository
        self._get_profiles = get_profiles
        self._get_user_profiles = get_user_profiles
        self._recover_tasks = recover_tasks

    def list_sessions(self) -> list[ChatSessionSummary]:
        return self._get_repository().list()

    def create_session(self, request: CreateSessionRequest) -> ChatSession:
        try:
            config = (
                self._get_profiles()[request.profile_name]
                if request.profile_name is not None
                else request.config
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown profile: {request.profile_name}",
            ) from error
        try:
            if (
                request.user_profile_id is not None
                and self._get_user_profiles().get(request.user_profile_id) is None
            ):
                raise user_profile_error(
                    "user_profile_not_found", "User profile was not found", 404
                )
        except UserProfileStorageError as error:
            raise user_profile_error(
                "user_profile_unavailable", "User profiles are unavailable", 500
            ) from error
        assert config is not None
        now = datetime.now(UTC)
        session = ChatSession(
            id=str(uuid.uuid4()),
            config=config,
            profile_name=request.profile_name,
            user_profile_id=request.user_profile_id,
            task_mode_enabled=request.task_mode_enabled,
            created_at=now,
            updated_at=now,
        )
        self._get_repository().save(session)
        return session

    def get_session(self, session_id: str) -> ChatSession:
        try:
            validate_path_identifier(session_id, "session ID")
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid session ID") from error
        session = self._get_repository().load(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
        self._recover_tasks(session_id, session)
        return session

    def list_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions",
            self.list_sessions,
            methods=["GET"],
            response_model=list[ChatSessionSummary],
        )
        return router

    def detail_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions",
            self.create_session,
            methods=["POST"],
            response_model=ChatSession,
            status_code=status.HTTP_201_CREATED,
        )
        router.add_api_route(
            "/sessions/{session_id}", self.get_session, methods=["GET"], response_model=ChatSession
        )
        return router
