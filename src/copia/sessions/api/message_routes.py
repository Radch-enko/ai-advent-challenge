import time
from collections.abc import Callable

from fastapi import BackgroundTasks, HTTPException, status

from copia.agents.application.agent_runtime import (
    FactsUpdateFailed,
    SummarizationFailed,
    SummarizationRetryRequired,
)
from copia.document_indexing.domain.errors import DocumentRetrievalError
from copia.providers.application.collect_streamed_response import collect_streamed_response
from copia.providers.data.llm import ProviderError
from copia.sessions.api.message_dependencies import SessionMessageDependencies
from copia.sessions.api.models.message_request import MessageRequest
from copia.sessions.api.models.session_message_response import SessionMessageResponse
from copia.sessions.application.agent_builder import build_session_agent
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class SessionMessageRoutes:
    def __init__(self, get_dependencies: Callable[[], SessionMessageDependencies]) -> None:
        self._get_dependencies = get_dependencies

    async def validate_streaming_message(self, session_id: str) -> None:
        runtime = self._get_dependencies()
        message_lock = runtime.get_lock(session_id)
        await runtime.threadpool(message_lock.lock.acquire)
        try:
            session = await runtime.get_session(session_id)
            if runtime.has_active_task(session):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "task_active",
                        "message": "A task is active for this session; resume or wait for it to finish",
                    },
                )
            await runtime.load_profile(session)
        finally:
            message_lock.lock.release()
            runtime.release_lock(message_lock)

    async def execute_streaming_message(
        self,
        session_id: str,
        request: MessageRequest,
        emit: Callable[[str, dict], None],
    ) -> SessionMessageResponse:
        runtime = self._get_dependencies()
        message_lock = runtime.get_lock(session_id)
        await runtime.threadpool(message_lock.lock.acquire)
        try:

            def completion(messages, config):
                return collect_streamed_response(runtime.llm_router, messages, config, emit)

            background = BackgroundTasks()
            response = await self._send_session_message_locked(
                session_id, request, background, completion=completion
            )
            await background()
            return response
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
            raise runtime.initialization_error(
                "Session is unavailable", "session_unavailable"
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
                    "code": "conversation_required",
                    "message": "MCP-enabled agents must use the asynchronous turn API",
                },
            )
        if runtime.has_active_task(session):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A task is active for this session; resume or wait for it to finish",
            )
        started_at = time.perf_counter()
        completion, sources = await self._prepare_rag(runtime, session, request.content, completion)
        if request.config is not None and session.profile_name is None:
            session.config = request.config
        user_profile = await runtime.load_profile(session)
        try:
            facts = await runtime.threadpool(runtime.sessions.load_facts, session.id)
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                "Session facts are unavailable", "session_facts_unavailable"
            ) from error
        try:
            long_term_memory = await runtime.threadpool(runtime.load_longterm, session, facts)
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                "Long-term memory is unavailable", "long_term_memory_unavailable"
            ) from error
        try:
            loaded_working_memory = await runtime.threadpool(
                runtime.memory_access.load_working, session.id
            )
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                "Working memory is unavailable", "working_memory_unavailable"
            ) from error
        try:
            loaded_pending_memory = await runtime.threadpool(
                runtime.memory_access.load_pending, session.id
            )
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                "Pending memory is unavailable", "pending_memory_unavailable"
            ) from error
        try:
            loaded_invariants = await runtime.threadpool(runtime.invariants.load)
        except (OSError, ValueError) as error:
            raise runtime.initialization_error(
                "Invariants are unavailable", "invariants_unavailable"
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
                "Agent initialization failed", "agent_initialization_failed"
            ) from error
        try:
            response = await runtime.threadpool(
                runtime.ask_agent,
                session.id,
                agent,
                request.content,
                True,
                completion,
            )
        except FactsUpdateFailed as error:
            runtime.save_agent(session, agent)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Facts update failed",
                    "code": "facts_update_failed",
                    "facts_event": runtime.safe_facts([error.event])[0].model_dump(mode="json"),
                },
            ) from error
        except SummarizationFailed as error:
            runtime.save_agent(session, agent)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Conversation summarization failed",
                    "code": "summarization_failed",
                    "summarization_event": runtime.safe_summary([error.event])[0].model_dump(
                        mode="json"
                    ),
                },
            ) from error
        except SummarizationRetryRequired as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Summarization retry required",
                    "code": "summarization_retry_required",
                },
            ) from error
        except ProviderError as error:
            runtime.save_agent(session, agent)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Provider request failed",
                    "code": "provider_request_failed",
                },
            ) from error

        if sources:
            agent.attach_sources_to_last_response(sources)
        runtime.save_agent(session, agent)
        if session.title is None:
            background_tasks.add_task(runtime.generate_title, session.id)
        return runtime.make_response(
            response,
            time.perf_counter() - started_at,
            summarization_events=agent.operation_events,
            facts_events=agent.facts_operation_events,
            facts=agent.facts,
            memory_events=agent.memory_events,
            pending_memory=agent.pending_memory,
            working_memory=agent.working_memory,
            sources=sources,
        )

    async def retry_session_summarization(
        self, session_id: str, completion=None
    ) -> SessionMessageResponse:
        runtime = self._get_dependencies()
        # Выполняем чтение, retry и сохранение под той же блокировкой, что и отправку.
        message_lock = runtime.get_lock(session_id)
        await runtime.threadpool(message_lock.lock.acquire)
        try:
            try:
                session = await runtime.get_session(session_id)
            except (OSError, ValueError) as error:
                validate_path_identifier(session_id, "session ID")
                raise runtime.initialization_error(
                    "Session is unavailable", "session_unavailable"
                ) from error
            started_at = time.perf_counter()
            query = next(
                (
                    message.content
                    for message in reversed(session.messages)
                    if message.role == "user"
                ),
                "",
            )
            completion, sources = await self._prepare_rag(runtime, session, query, completion)
            user_profile = await runtime.load_profile(session)
            try:
                facts = await runtime.threadpool(runtime.sessions.load_facts, session.id)
                long_term_memory = await runtime.threadpool(runtime.load_longterm, session, facts)
            except (OSError, ValueError) as error:
                raise runtime.initialization_error(
                    "Session memory is unavailable", "session_memory_unavailable"
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
                    "Session context is unavailable", "session_context_unavailable"
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
                    "Agent initialization failed", "agent_initialization_failed"
                ) from error
            try:
                response = await runtime.threadpool(
                    runtime.retry_agent, session.id, agent, True, completion
                )
            except SummarizationFailed as error:
                runtime.save_agent(session, agent)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "message": "Conversation summarization failed",
                        "code": "summarization_failed",
                        "summarization_event": runtime.safe_summary([error.event])[0].model_dump(
                            mode="json"
                        ),
                    },
                ) from error
            except SummarizationRetryRequired as error:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Summarization retry required",
                        "code": "summarization_retry_required",
                    },
                ) from error
            except ProviderError as error:
                runtime.save_agent(session, agent)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "message": "Provider request failed",
                        "code": "provider_request_failed",
                    },
                ) from error

            if sources:
                agent.attach_sources_to_last_response(sources)
            runtime.save_agent(session, agent)
            return runtime.make_response(
                response,
                time.perf_counter() - started_at,
                summarization_events=agent.operation_events,
                facts_events=agent.facts_operation_events,
                facts=agent.facts,
                memory_events=agent.memory_events,
                pending_memory=agent.pending_memory,
                working_memory=agent.working_memory,
                sources=sources,
            )
        finally:
            message_lock.lock.release()
            runtime.release_lock(message_lock)

    async def _prepare_rag(self, runtime, session, query: str, completion):
        if not session.rag_enabled:
            return completion, []
        try:
            chunk = await runtime.threadpool(runtime.retrieve_chunk, query)
        except DocumentRetrievalError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "rag_unavailable", "message": str(error)},
            ) from error
        base_completion = completion or runtime.llm_router.complete

        def complete_with_rag(messages, config):
            return base_completion(runtime.contextualize(messages, chunk), config)

        return complete_with_rag, [chunk.source]
