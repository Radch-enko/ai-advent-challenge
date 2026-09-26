from collections.abc import Callable
from typing import Any

from copia.agents.domain.models.agent import Agent
from copia.invariants.domain.models.invariant import Invariant
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.providers.application.llm_router import LLMRouter
from copia.providers.data.model_catalog import context_window_for
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.domain.models.chat_session import ChatSession
from copia.user_profiles.domain.models.user_profile import UserProfile


def build_session_agent(
    session: ChatSession,
    router: LLMRouter,
    working_memory_store: WorkingMemoryRepository,
    facts: dict[str, str],
    long_term_memory: list[LongTermMemoryItem],
    loaded_working_memory: list[WorkingMemoryItem],
    loaded_pending_memory: list[PendingMemorySuggestion],
    loaded_invariants: list[Invariant],
    user_profile: UserProfile | None,
    make_agent: Callable[..., Agent],
    make_classifier: Callable[..., Any],
) -> Agent:
    return make_agent(
        config=session.config,
        router=router,
        history=session.messages,
        context=session.context,
        facts=facts,
        long_term_memory=long_term_memory,
        context_window=context_window_for(session.config.provider, session.config.model),
        working_memory=loaded_working_memory,
        working_memory_store=working_memory_store,
        session_id=session.id,
        memory_classifier=(
            make_classifier(router, session.config, loaded_invariants)
            if loaded_invariants
            else make_classifier(router, session.config)
        ),
        pending_memory=loaded_pending_memory,
        user_profile=user_profile,
        invariants=loaded_invariants,
    )
