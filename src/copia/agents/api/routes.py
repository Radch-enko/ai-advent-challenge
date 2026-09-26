from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status

from copia.agents.api.agent_route_runtime import AgentRouteRuntime
from copia.agents.api.models.create_agent_request import CreateAgentRequest
from copia.agents.api.models.create_agent_response import CreateAgentResponse
from copia.agents.domain.models.agent_config import AgentConfig
from copia.providers.data.llm import ProviderError
from copia.sessions.api.models.message_request import MessageRequest
from copia.sessions.api.models.message_response import MessageResponse


class AgentRoutes:
    def __init__(self, get_runtime: Callable[[], AgentRouteRuntime]) -> None:
        self._get_runtime = get_runtime

    def profiles_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/profiles", self.profiles, methods=["GET"])
        return router

    def create_message_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/agents",
            self.create_agent,
            methods=["POST"],
            response_model=CreateAgentResponse,
            status_code=status.HTTP_201_CREATED,
        )
        router.add_api_route(
            "/agents/{agent_id}/messages",
            self.send_message,
            methods=["POST"],
            response_model=MessageResponse,
        )
        return router

    def delete_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/agents/{agent_id}",
            self.delete_agent,
            methods=["DELETE"],
            status_code=status.HTTP_204_NO_CONTENT,
        )
        return router

    def profiles(self) -> dict[str, AgentConfig]:
        return self._get_runtime().factory.profiles()

    def create_agent(self, request: CreateAgentRequest) -> CreateAgentResponse:
        runtime = self._get_runtime()
        try:
            loaded_invariants = runtime.invariants.load()
            if request.profile_name is not None:
                agent = runtime.factory.create_from_profile(request.profile_name)
                agent = runtime.make_agent(
                    config=agent.config,
                    router=runtime.router,
                    long_term_memory_loader=(
                        (lambda: runtime.profile_memory.load(request.profile_name))
                        if request.long_term_memory_enabled
                        else None
                    ),
                    context_window=runtime.context_window_for(
                        agent.config.provider, agent.config.model
                    ),
                )
            else:
                agent = runtime.factory.create(request.config)  # type: ignore[arg-type]
            agent.set_invariants(loaded_invariants)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except (OSError, ValueError) as error:
            raise runtime.memory_storage_error() from error

        agent_id = str(uuid.uuid4())
        runtime.agents[agent_id] = agent
        return CreateAgentResponse(
            agent_id=agent_id,
            config=agent.config,
            long_term_memory_enabled=request.long_term_memory_enabled,
        )

    async def send_message(self, agent_id: str, request: MessageRequest) -> MessageResponse:
        runtime = self._get_runtime()
        agent = runtime.agents.get(agent_id)
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
        if agent.config.mcp_access:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "mcp_turn_required",
                    "message": "MCP-enabled agents must use a persisted session turn",
                },
            )
        try:
            loaded_invariants = await runtime.threadpool(runtime.invariants.load)
            agent.set_invariants(loaded_invariants)
            response = await runtime.threadpool(agent.ask, request.content)
        except ProviderError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=runtime.provider_error_detail(
                    error, redact_request=agent.has_long_term_memory
                ),
            ) from error
        except (OSError, ValueError) as error:
            raise runtime.memory_storage_error() from error
        return MessageResponse(response=response, memory_events=agent.memory_events)

    def delete_agent(self, agent_id: str) -> None:
        if self._get_runtime().agents.pop(agent_id, None) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
