from __future__ import annotations

from types import ModuleType
from typing import Self

from copia.session_memory.api.models.session_memory_service_bindings import (
    SessionMemoryServiceBindings,
)
from copia.session_memory.api.pending_memory_routes import PendingMemoryRoutes
from copia.session_memory.api.working_memory_routes import WorkingMemoryRoutes


class SessionMemoryServiceComposition:
    @classmethod
    def from_service(cls, service: ModuleType) -> Self:
        return cls(
            SessionMemoryServiceBindings(
                _get_session=lambda: service._get_session,
                _get_session_locked=lambda: service._get_session_locked,
                _session_mutation_lock=lambda: service._session_mutation_lock,
                approved_memory_cache=lambda: service.approved_memory_cache,
                approved_memory_mutations=lambda: service.approved_memory_mutations,
                pending_memory=lambda: service.pending_memory,
                pending_memory_repository=lambda: service.pending_memory_repository,
                profile_memory=lambda: service.profile_memory,
                run_in_threadpool=lambda: service.run_in_threadpool,
                working_memory=lambda: service.working_memory,
            )
        )

    def __init__(self, bindings: SessionMemoryServiceBindings) -> None:
        self._bindings = bindings

    def working_routes(self) -> WorkingMemoryRoutes:
        service = self._bindings
        return WorkingMemoryRoutes(
            lambda: service.working_memory(),
            service._get_session(),
            service._get_session_locked(),
            service._session_mutation_lock(),
            lambda: service.run_in_threadpool(),
        )

    def pending_routes(self) -> PendingMemoryRoutes:
        service = self._bindings
        return PendingMemoryRoutes(
            lambda: service.pending_memory_repository(),
            lambda: service.profile_memory(),
            lambda: service.pending_memory(),
            lambda: service.approved_memory_mutations(),
            service.approved_memory_cache().put,
            service._get_session(),
            service._get_session_locked(),
            service._session_mutation_lock(),
            lambda: service.run_in_threadpool(),
        )
