from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.agents.domain.models.agent import Agent, AgentFactory
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.providers.application.llm_router import LLMRouter
from copia.providers.domain.models.provider_name import ProviderName


@dataclass(frozen=True)
class AgentRouteRuntime:
    factory: AgentFactory
    router: LLMRouter
    invariants: InvariantsRepository
    profile_memory: ProfileMemoryRepository
    agents: dict[str, Agent]
    threadpool: Callable[..., Awaitable[Any]]
    make_agent: Callable[..., Agent]
    context_window_for: Callable[[ProviderName, str], int | None]
    provider_error_detail: Callable[..., dict[str, object]]
    memory_storage_error: Callable[[], Exception]
