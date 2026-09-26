from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.providers.application.llm_router import LLMRouter
from copia.providers.data.llm import ProviderError


@dataclass(frozen=True)
class ProviderRouteRuntime:
    router: LLMRouter
    invariants: InvariantsRepository
    threadpool: Callable[..., Awaitable[Any]]
    provider_error_detail: Callable[[ProviderError], dict[str, object]]
    memory_storage_error: Callable[[], Exception]
