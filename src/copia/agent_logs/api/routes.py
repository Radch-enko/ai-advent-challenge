from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, status

from copia.agent_logs.api.mappers.agent_log_response import agent_log_response
from copia.agent_logs.api.models.agent_log_response import AgentLogResponse
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.sessions.domain.models.chat_session import ChatSession
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class AgentLogRoutes:
    def __init__(
        self,
        get_session: Callable[[], Callable[[str], Awaitable[ChatSession]]],
        get_store: Callable[[], AgentLogStore],
        get_threadpool: Callable[[], Callable[..., Awaitable[Any]]],
    ) -> None:
        self._get_session = get_session
        self._get_store = get_store
        self._get_threadpool = get_threadpool

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/agent-logs/{agent_log_id}",
            self.get_agent_log,
            methods=["GET"],
            response_model=AgentLogResponse,
        )
        return router

    async def get_agent_log(self, session_id: str, agent_log_id: str) -> AgentLogResponse:
        await self._get_session()(session_id)
        try:
            validate_path_identifier(agent_log_id, "agent log ID")
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid agent log ID") from error
        turn = await self._get_threadpool()(self._get_store().get_turn, session_id, agent_log_id)
        if turn is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Agent log is unavailable"
            )
        return agent_log_response(turn)
