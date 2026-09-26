from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from copia.agents.domain.models.agent import (
    FactsUpdateFailed,
    SummarizationFailed,
    SummarizationRetryRequired,
)
from copia.providers.data.llm import ProviderError
from copia.sessions.api.message_dependencies import SessionMessageDependencies
from copia.sessions.api.models.message_request import MessageRequest
from copia.sessions.api.models.session_message_response import SessionMessageResponse
from copia.sessions.application.agent_builder import build_session_agent
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class SessionMessageRoutes:
    def __init__(self, get_dependencies: Callable[[], SessionMessageDependencies]) -> None:
        self._get_dependencies = get_dependencies

    def send_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/messages",
            self.send_session_message,
            methods=["POST"],
            response_model=SessionMessageResponse,
        )
        return router

    def retry_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/summarization/retry",
            self.retry_session_summarization,
            methods=["POST"],
            response_model=SessionMessageResponse,
        )
        return router

    async def send_session_message(
        self, session_id: str, request: MessageRequest, background_tasks: BackgroundTasks
    ) -> SessionMessageResponse:
        runtime = self._get_dependencies()
        # Ждём блокировку вне event loop: другой запрос может обращаться к провайдеру.
        message_lock = runtime.get_lock(session_id)
        await runtime.threadpool(message_lock.lock.acquire)
        try:
            return await self._send_session_message_locked(session_id, request, background_tasks)
        finally:
            message_lock.lock.release()
            runtime.release_lock(message_lock)

    async def _send_session_message_locked(
        self,
        session_id: str,
        request: MessageRequest,
        background_tasks: BackgroundTasks,
        completion=None,
    ) -> SessionMessageResponse:
        runtime = self._get_dependencies()
        try:
            session = await runtime.get_session(session_id)
        except (OSError, ValueError) as error:
            validate_path_identifier(session_id, "session ID")
            agent_log_id = runtime.agent_logs.start_turn(session_id)
            raise runtime.initialization_error(
                agent_log_id, "Session is unavailable", "session_unavailable"
            ) from error
        effective_config = (
            request.config
            if request.config is not None and session.profile_name is None
            else session.config
        )
        if completion is None and effective_config.mcp_access:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "mcp_turn_required",
                    "message": "MCP-enabled agents must use the asynchronous turn API",
                },
            )
        if runtime.has_active_task(session):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A task is active for this session; resume or wait for it to finish",
            )
        agent_log_id = runtime.agent_logs.start_turn(session.id)
        if request.config is not None and session.profile_name is None:
            session.config = request.config
        user_profile = await runtime.load_profile(session, agent_log_id)
        try:
            facts = await runtime.threadpool(runtime.sessions.load_facts, session.id)
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                agent_log_id, "Session facts are unavailable", "session_facts_unavailable"
            ) from error
        try:
            long_term_memory = await runtime.threadpool(runtime.load_longterm, session, facts)
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                agent_log_id, "Long-term memory is unavailable", "long_term_memory_unavailable"
            ) from error
        try:
            loaded_working_memory = await runtime.threadpool(
                runtime.memory_access.load_working, session.id
            )
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                agent_log_id, "Working memory is unavailable", "working_memory_unavailable"
            ) from error
        try:
            loaded_pending_memory = await runtime.threadpool(
                runtime.memory_access.load_pending, session.id
            )
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                agent_log_id, "Pending memory is unavailable", "pending_memory_unavailable"
            ) from error
        try:
            loaded_invariants = await runtime.threadpool(runtime.invariants.load)
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                agent_log_id, "Invariants are unavailable", "invariants_unavailable"
            ) from error
        try:
            agent = build_session_agent(
                session,
                runtime.llm_router,
                runtime.working_memory,
                facts,
                long_term_memory,
                loaded_working_memory,
                loaded_pending_memory,
                loaded_invariants,
                user_profile,
                runtime.make_agent,
                runtime.make_classifier,
            )
        except (OSError, TypeError, ValueError) as error:
            raise runtime.initialization_error(
                agent_log_id, "Agent initialization failed", "agent_initialization_failed"
            ) from error
        try:
            response = await runtime.threadpool(
                runtime.ask_agent,
                session.id,
                agent,
                request.content,
                agent_log_id,
                True,
                completion,
            )
        except FactsUpdateFailed as error:
            runtime.save_agent(session, agent)
            runtime.finish_log(
                agent_log_id,
                provider=error.event.provider,
                model=error.event.model,
                status="failed",
                error="Facts update failed",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Facts update failed",
                    "code": "facts_update_failed",
                    "agent_log_id": agent_log_id,
                    "facts_event": runtime.safe_facts([error.event])[0].model_dump(mode="json"),
                },
            ) from error
        except SummarizationFailed as error:
            runtime.save_agent(session, agent)
            runtime.finish_log(
                agent_log_id,
                provider=error.event.provider,
                model=error.event.model,
                status="failed",
                error="Conversation summarization failed",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Conversation summarization failed",
                    "code": "summarization_failed",
                    "agent_log_id": agent_log_id,
                    "summarization_event": runtime.safe_summary([error.event])[0].model_dump(
                        mode="json"
                    ),
                },
            ) from error
        except SummarizationRetryRequired as error:
            runtime.finish_log(agent_log_id, status="failed", error="Summarization retry required")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Summarization retry required",
                    "code": "summarization_retry_required",
                    "agent_log_id": agent_log_id,
                },
            ) from error
        except ProviderError as error:
            runtime.save_agent(session, agent)
            runtime.finish_log(
                agent_log_id,
                provider=session.config.provider,
                model=session.config.model,
                status="failed",
                error="Provider request failed",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Provider request failed",
                    "code": "provider_request_failed",
                    "agent_log_id": agent_log_id,
                    "provider_trace": runtime.failure_trace(error).model_dump(mode="json"),
                },
            ) from error

        runtime.save_agent(session, agent)
        runtime.finish_log(
            agent_log_id,
            provider=response.provider,
            model=response.model,
            usage=response.usage,
            status="completed",
        )
        if session.title is None:
            background_tasks.add_task(runtime.generate_title, session.id, agent_log_id)
        return runtime.make_response(
            response,
            agent_log_id,
            summarization_events=agent.operation_events,
            facts_events=agent.facts_operation_events,
            facts=agent.facts,
            memory_events=agent.memory_events,
            pending_memory=agent.pending_memory,
            working_memory=agent.working_memory,
        )

    async def retry_session_summarization(self, session_id: str) -> SessionMessageResponse:
        runtime = self._get_dependencies()
        # Выполняем чтение, retry и сохранение под той же блокировкой, что и отправку.
        message_lock = runtime.get_lock(session_id)
        await runtime.threadpool(message_lock.lock.acquire)
        try:
            try:
                session = await runtime.get_session(session_id)
            except (OSError, ValueError) as error:
                validate_path_identifier(session_id, "session ID")
                agent_log_id = runtime.agent_logs.start_turn(session_id)
                raise runtime.initialization_error(
                    agent_log_id, "Session is unavailable", "session_unavailable"
                ) from error
            agent_log_id = runtime.agent_logs.start_turn(session.id)
            user_profile = await runtime.load_profile(session, agent_log_id)
            try:
                facts = await runtime.threadpool(runtime.sessions.load_facts, session.id)
                long_term_memory = await runtime.threadpool(runtime.load_longterm, session, facts)
            except (OSError, ValueError) as error:
                raise runtime.initialization_error(
                    agent_log_id, "Session memory is unavailable", "session_memory_unavailable"
                ) from error
            try:
                loaded_working_memory = await runtime.threadpool(
                    runtime.memory_access.load_working, session.id
                )
                loaded_pending_memory = await runtime.threadpool(
                    runtime.memory_access.load_pending, session.id
                )
                loaded_invariants = await runtime.threadpool(runtime.invariants.load)
            except (OSError, ValueError) as error:
                raise runtime.initialization_error(
                    agent_log_id, "Session context is unavailable", "session_context_unavailable"
                ) from error
            try:
                agent = build_session_agent(
                    session,
                    runtime.llm_router,
                    runtime.working_memory,
                    facts,
                    long_term_memory,
                    loaded_working_memory,
                    loaded_pending_memory,
                    loaded_invariants,
                    user_profile,
                    runtime.make_agent,
                    runtime.make_classifier,
                )
            except (OSError, TypeError, ValueError) as error:
                raise runtime.initialization_error(
                    agent_log_id, "Agent initialization failed", "agent_initialization_failed"
                ) from error
            try:
                response = await runtime.threadpool(
                    runtime.retry_agent, session.id, agent, agent_log_id, True
                )
            except SummarizationFailed as error:
                runtime.save_agent(session, agent)
                runtime.finish_log(
                    agent_log_id,
                    provider=error.event.provider,
                    model=error.event.model,
                    status="failed",
                    error="Conversation summarization failed",
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "message": "Conversation summarization failed",
                        "code": "summarization_failed",
                        "agent_log_id": agent_log_id,
                        "summarization_event": runtime.safe_summary([error.event])[0].model_dump(
                            mode="json"
                        ),
                    },
                ) from error
            except SummarizationRetryRequired as error:
                runtime.finish_log(
                    agent_log_id, status="failed", error="Summarization retry required"
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Summarization retry required",
                        "code": "summarization_retry_required",
                        "agent_log_id": agent_log_id,
                    },
                ) from error
            except ProviderError as error:
                runtime.save_agent(session, agent)
                runtime.finish_log(
                    agent_log_id,
                    provider=session.config.provider,
                    model=session.config.model,
                    status="failed",
                    error="Provider request failed",
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "message": "Provider request failed",
                        "code": "provider_request_failed",
                        "agent_log_id": agent_log_id,
                        "provider_trace": runtime.failure_trace(error).model_dump(mode="json"),
                    },
                ) from error

            runtime.save_agent(session, agent)
            runtime.finish_log(
                agent_log_id,
                provider=response.provider,
                model=response.model,
                usage=response.usage,
                status="completed",
            )
            return runtime.make_response(
                response,
                agent_log_id,
                summarization_events=agent.operation_events,
                facts_events=agent.facts_operation_events,
                facts=agent.facts,
                memory_events=agent.memory_events,
                pending_memory=agent.pending_memory,
                working_memory=agent.working_memory,
            )
        finally:
            message_lock.lock.release()
            runtime.release_lock(message_lock)
