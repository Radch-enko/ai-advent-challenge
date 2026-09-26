from __future__ import annotations

from types import ModuleType
from typing import Self

from fastapi import HTTPException, status

from copia.sessions.api.collection_routes import SessionCollectionRoutes
from copia.sessions.api.deletion_routes import SessionDeletionRoutes
from copia.sessions.api.message_dependencies import SessionMessageDependencies
from copia.sessions.api.message_errors import SessionMessageErrors
from copia.sessions.api.message_routes import SessionMessageRoutes
from copia.sessions.api.models.session_service_bindings import SessionServiceBindings
from copia.sessions.api.session_access import SessionAccess
from copia.sessions.api.session_access_runtime import SessionAccessRuntime
from copia.sessions.api.settings_routes import SessionSettingsRoutes
from copia.sessions.api.turn_profile_loader import TurnProfileLoader
from copia.sessions.application.session_agent_execution import SessionAgentExecution
from copia.sessions.application.session_long_term_memory_access import SessionLongTermMemoryAccess
from copia.sessions.application.session_title_generator import SessionTitleGenerator


class SessionServiceComposition:
    @classmethod
    def from_service(cls, service: ModuleType) -> Self:
        return cls(
            SessionServiceBindings(
                Agent=lambda: service.Agent,
                LLMMemoryClassifier=lambda: service.LLMMemoryClassifier,
                _ask_agent=lambda: service._ask_agent,
                _finish_agent_log=lambda: service._finish_agent_log,
                _get_session=lambda: service._get_session,
                _get_session_locked=lambda: service._get_session_locked,
                _load_user_profile_for_turn=lambda: service._load_user_profile_for_turn,
                _long_term_memory_for_session=lambda: service._long_term_memory_for_session,
                _recover_orphaned_session_tasks=lambda: service._recover_orphaned_session_tasks,
                _release_session_message_lock=lambda: service._release_session_message_lock,
                _retry_agent=lambda: service._retry_agent,
                _safe_facts_events=lambda: service._safe_facts_events,
                _safe_summarization_events=lambda: service._safe_summarization_events,
                _save_agent_state=lambda: service._save_agent_state,
                _session_failure_trace=lambda: service._session_failure_trace,
                _session_initialization_error=lambda: service._session_initialization_error,
                _session_message_lock=lambda: service._session_message_lock,
                _session_message_response=lambda: service._session_message_response,
                _session_mutation_lock=lambda: service._session_mutation_lock,
                agent_log_store=lambda: service.agent_log_store,
                approved_memory_mutations=lambda: service.approved_memory_mutations,
                factory=lambda: service.factory,
                generate_session_title=lambda: service.generate_session_title,
                invariants_repository=lambda: service.invariants_repository,
                mcp_turns=lambda: service.mcp_turns,
                mcp_turns_lock=lambda: service.mcp_turns_lock,
                pending_memory=lambda: service.pending_memory,
                pending_memory_repository=lambda: service.pending_memory_repository,
                profile_memory=lambda: service.profile_memory,
                router=lambda: service.router,
                run_in_threadpool=lambda: service.run_in_threadpool,
                session_lifecycle_lock=lambda: service.session_lifecycle_lock,
                session_memory_access=lambda: service.session_memory_access,
                session_message_locks=lambda: service.session_message_locks,
                sessions=lambda: service.sessions,
                task_state_rules=lambda: service.task_state_rules,
                user_profiles=lambda: service.user_profiles,
                working_memory=lambda: service.working_memory,
            )
        )

    def __init__(self, bindings: SessionServiceBindings) -> None:
        self._bindings = bindings

    def message_errors(self) -> SessionMessageErrors:
        return SessionMessageErrors(lambda: self._bindings._finish_agent_log())

    def turn_profile_loader(self) -> TurnProfileLoader:
        service = self._bindings
        return TurnProfileLoader(
            lambda: service.user_profiles(),
            lambda: service.agent_log_store(),
            lambda: service.run_in_threadpool(),
            lambda: service._session_initialization_error(),
        )

    def collection_routes(self) -> SessionCollectionRoutes:
        service = self._bindings
        return SessionCollectionRoutes(
            lambda: service.sessions(),
            service.factory().profiles,
            lambda: service.user_profiles(),
            service._recover_orphaned_session_tasks(),
        )

    def access_runtime(self) -> SessionAccessRuntime:
        service = self._bindings
        return SessionAccessRuntime(
            sessions=service.sessions(),
            threadpool=service.run_in_threadpool(),
            mcp_turns=service.mcp_turns(),
            mcp_turns_lock=service.mcp_turns_lock(),
            lifecycle_lock=service.session_lifecycle_lock(),
            message_locks=service.session_message_locks(),
        )

    def access(self) -> SessionAccess:
        return SessionAccess(self.access_runtime)

    def settings_routes(self) -> SessionSettingsRoutes:
        service = self._bindings
        return SessionSettingsRoutes(
            lambda: service.sessions(),
            lambda: service.user_profiles(),
            service._get_session(),
            service._get_session_locked(),
            service._session_mutation_lock(),
            lambda: service.session_lifecycle_lock(),
            lambda: service.run_in_threadpool(),
        )

    def message_dependencies(self) -> SessionMessageDependencies:
        service = self._bindings
        return SessionMessageDependencies(
            get_session=service._get_session(),
            get_lock=service._session_message_lock(),
            release_lock=service._release_session_message_lock(),
            threadpool=service.run_in_threadpool(),
            sessions=service.sessions(),
            agent_logs=service.agent_log_store(),
            memory_access=service.session_memory_access(),
            invariants=service.invariants_repository(),
            llm_router=service.router(),
            working_memory=service.working_memory(),
            make_agent=service.Agent(),
            make_classifier=service.LLMMemoryClassifier(),
            initialization_error=service._session_initialization_error(),
            has_active_task=service.task_state_rules().session_has_active_task,
            load_profile=service._load_user_profile_for_turn(),
            load_longterm=service._long_term_memory_for_session(),
            ask_agent=service._ask_agent(),
            retry_agent=service._retry_agent(),
            save_agent=service._save_agent_state(),
            finish_log=service._finish_agent_log(),
            safe_facts=service._safe_facts_events(),
            safe_summary=service._safe_summarization_events(),
            failure_trace=service._session_failure_trace(),
            make_response=service._session_message_response(),
            generate_title=service.generate_session_title(),
        )

    def message_routes(self) -> SessionMessageRoutes:
        return SessionMessageRoutes(self.message_dependencies)

    def deletion_routes(self) -> SessionDeletionRoutes:
        service = self._bindings
        return SessionDeletionRoutes(
            lambda: service.sessions(),
            lambda session_id: service.agent_log_store().delete_session(session_id),
            lambda session_id: service.working_memory().delete(session_id),
            lambda session_id: service.pending_memory_repository().delete(session_id),
            lambda: service.pending_memory(),
            lambda: service.approved_memory_mutations(),
            service._session_message_lock(),
            service._release_session_message_lock(),
            lambda: service.session_lifecycle_lock(),
        )

    def title_generator(self) -> SessionTitleGenerator:
        service = self._bindings
        return SessionTitleGenerator(
            lambda: service.sessions(),
            lambda: service.invariants_repository(),
            lambda: service.router(),
            lambda: service.session_lifecycle_lock(),
        )

    def agent_execution(self) -> SessionAgentExecution:
        service = self._bindings
        return SessionAgentExecution(
            lambda: service.sessions(),
            lambda: service.session_memory_access(),
            service._session_message_lock(),
            service._release_session_message_lock(),
            lambda: service.session_lifecycle_lock(),
            lambda: HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session"),
        )

    def long_term_memory_access(self) -> SessionLongTermMemoryAccess:
        return SessionLongTermMemoryAccess(lambda: self._bindings.profile_memory())
