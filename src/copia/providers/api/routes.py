from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status

from copia.providers.api.models.completion_request import CompletionRequest
from copia.providers.api.provider_route_runtime import ProviderRouteRuntime
from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.provider_capabilities import ProviderCapabilities
from copia.providers.domain.models.provider_model import ProviderModel
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.api.models.message_response import MessageResponse
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.services.context_strategy import render_invariants_context


class ProviderRoutes:
    def __init__(self, get_runtime: Callable[[], ProviderRouteRuntime]) -> None:
        self._get_runtime = get_runtime

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/providers/{provider_name}/capabilities",
            self.capabilities,
            methods=["GET"],
        )
        router.add_api_route(
            "/providers/{provider_name}/models",
            self.models,
            methods=["GET"],
            response_model=list[ProviderModel],
        )
        router.add_api_route(
            "/completions",
            self.completion,
            methods=["POST"],
            response_model=MessageResponse,
        )
        return router

    def capabilities(self, provider_name: ProviderName) -> ProviderCapabilities:
        try:
            return self._get_runtime().router.capabilities(provider_name)
        except ProviderError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Provider is unavailable"
            ) from error

    async def models(self, provider_name: ProviderName) -> list[ProviderModel]:
        runtime = self._get_runtime()
        try:
            return await runtime.threadpool(runtime.router.models, provider_name)
        except ProviderError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=runtime.provider_error_detail(error),
            ) from error

    async def completion(self, request: CompletionRequest) -> MessageResponse:
        runtime = self._get_runtime()
        messages = list(request.messages)
        try:
            invariant_context = render_invariants_context(runtime.invariants.load())
        except (OSError, ValueError) as error:
            raise runtime.memory_storage_error() from error
        system_content = "\n\n".join(
            part for part in (request.config.system_prompt, invariant_context) if part
        )
        if system_content:
            messages.insert(0, ChatMessage(role="system", content=system_content))
        try:
            response = await runtime.threadpool(runtime.router.complete, messages, request.config)
        except ProviderError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=runtime.provider_error_detail(error),
            ) from error
        return MessageResponse(response=response)
