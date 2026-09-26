from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.providers.domain.models.llm_response import LLMResponse
from copia.session_memory.application.session_memory_access import SessionMemoryAccess
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.sessions.api.models.session_message_response import SessionMessageResponse
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession


@dataclass(frozen=True)
class SessionMessageDependencies:
    get_session: Callable[[str], Awaitable[ChatSession]]
    get_lock: Callable[[str], Any]
    release_lock: Callable[[Any], None]
    threadpool: Callable[..., Awaitable[Any]]
    sessions: SessionsRepository
    agent_logs: AgentLogStore
    memory_access: SessionMemoryAccess
    invariants: InvariantsRepository
    llm_router: Any
    working_memory: WorkingMemoryRepository
    make_agent: Callable[..., Any]
    make_classifier: Callable[..., Any]
    initialization_error: Callable[..., HTTPException]
    has_active_task: Callable[[ChatSession], bool]
    load_profile: Callable[..., Awaitable[Any]]
    load_longterm: Callable[..., Any]
    ask_agent: Callable[..., LLMResponse]
    retry_agent: Callable[..., LLMResponse]
    save_agent: Callable[..., None]
    finish_log: Callable[..., None]
    safe_facts: Callable[..., Any]
    safe_summary: Callable[..., Any]
    failure_trace: Callable[..., Any]
    make_response: Callable[..., SessionMessageResponse]
    generate_title: Callable[..., None]
