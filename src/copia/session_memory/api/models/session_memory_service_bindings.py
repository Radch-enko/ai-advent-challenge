from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionMemoryServiceBindings:
    _get_session: Callable[[], Any]
    _get_session_locked: Callable[[], Any]
    _session_mutation_lock: Callable[[], Any]
    approved_memory_cache: Callable[[], Any]
    approved_memory_mutations: Callable[[], Any]
    pending_memory: Callable[[], Any]
    pending_memory_repository: Callable[[], Any]
    profile_memory: Callable[[], Any]
    run_in_threadpool: Callable[[], Any]
    working_memory: Callable[[], Any]
