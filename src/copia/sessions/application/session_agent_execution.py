from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from typing import Any

from copia.agent_logs.domain.services.agent_log_context import agent_log_turn
from copia.agents.domain.models.agent import Agent
from copia.providers.domain.models.llm_response import LLMResponse
from copia.session_memory.application.session_memory_access import SessionMemoryAccess
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.models.context_strategy_name import ContextStrategyName


class SessionAgentExecution:
    def __init__(
        self,
        get_repository: Callable[[], SessionsRepository],
        get_memory_access: Callable[[], SessionMemoryAccess],
        acquire_message_lock: Callable[[str], Any],
        release_message_lock: Callable[[Any], None],
        get_lifecycle_lock: Callable[[], AbstractContextManager[Any]],
        missing_session_error: Callable[[], Exception],
    ) -> None:
        self._get_repository = get_repository
        self._get_memory_access = get_memory_access
        self._acquire_message_lock = acquire_message_lock
        self._release_message_lock = release_message_lock
        self._get_lifecycle_lock = get_lifecycle_lock
        self._missing_session_error = missing_session_error

    def save_agent_state(self, session: ChatSession, agent: Agent) -> None:
        # Не восстанавливаем удалённую сессию после завершения запроса к провайдеру.
        with self._get_lifecycle_lock():
            repository = self._get_repository()
            if repository.load(session.id) is None:
                return
            session.messages = agent.history
            session.context = agent.context
            session.updated_at = datetime.now(UTC)
            repository.save(session)
            if session.config.context_management.strategy == ContextStrategyName.STICKY_FACTS:
                repository.save_facts(session.id, agent.facts)
            self._get_memory_access().save(session.id, agent.working_memory, agent.pending_memory)

    @contextmanager
    def _session_operation(self, session_id: str, lock_held: bool) -> Iterator[None]:
        message_lock = None if lock_held else self._acquire_message_lock(session_id)
        if message_lock is not None:
            message_lock.lock.acquire()
        try:
            with self._get_lifecycle_lock():
                if self._get_repository().load(session_id) is None:
                    raise self._missing_session_error()
            yield
        finally:
            if message_lock is not None:
                message_lock.lock.release()
                self._release_message_lock(message_lock)

    def ask_agent(
        self,
        session_id: str,
        agent: Agent,
        content: str,
        agent_log_id: str | None = None,
        session_lock_held: bool = False,
        completion: Callable[..., LLMResponse] | None = None,
    ) -> LLMResponse:
        with self._session_operation(session_id, session_lock_held):
            if agent_log_id is None:
                return (
                    agent.ask(content)
                    if completion is None
                    else agent.ask(content, completion=completion)
                )
            with agent_log_turn(
                session_id,
                agent_log_id,
                provider=agent.config.provider,
                model=agent.config.model,
            ):
                return (
                    agent.ask(content, agent_log_id=agent_log_id)
                    if completion is None
                    else agent.ask(content, agent_log_id=agent_log_id, completion=completion)
                )

    def retry_agent(
        self,
        session_id: str,
        agent: Agent,
        agent_log_id: str | None = None,
        session_lock_held: bool = False,
    ) -> LLMResponse:
        with self._session_operation(session_id, session_lock_held):
            if agent_log_id is None:
                return agent.retry_summarization()
            with agent_log_turn(
                session_id,
                agent_log_id,
                provider=agent.config.provider,
                model=agent.config.model,
                operation="retry",
            ):
                return agent.retry_summarization(agent_log_id=agent_log_id)
