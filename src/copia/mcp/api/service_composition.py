from __future__ import annotations

from types import ModuleType
from typing import Any, Self

from fastapi import BackgroundTasks

from copia.agents.data.profiles_repository import ProfilesRepository
from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.api.discovery import make_discover_connection
from copia.mcp.api.mappers.mcp_turn_response import make_mcp_turn_response
from copia.mcp.api.mcp_turn_route_runtime import McpTurnRouteRuntime
from copia.mcp.api.mcp_turn_routes import McpTurnRoutes
from copia.mcp.api.models.mcp_service_bindings import McpServiceBindings
from copia.mcp.api.models.mcp_turn_response import McpTurnResponse
from copia.mcp.application.mcp_tool_resolver import McpToolResolver
from copia.mcp.application.mcp_turn_state import McpTurnState
from copia.mcp.application.mcp_turn_worker import McpTurnWorker
from copia.mcp.application.mcp_turn_worker_runtime import McpTurnWorkerRuntime
from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime
from copia.mcp.data.mcp_tool_executor import McpToolExecutor
from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.security.domain.services.credential_sanitizer import sanitize_error


class McpServiceComposition:
    @classmethod
    def from_service(cls, service: ModuleType) -> Self:
        return cls(
            McpServiceBindings(
                _discover_connection=lambda: service._discover_connection,
                _emit_turn=lambda: service._emit_turn,
                _execute_resolved_tool=lambda: service._execute_resolved_tool,
                _get_session=lambda: service._get_session,
                _mcp_header=lambda: service._mcp_header,
                _persist_mcp_turn_state=lambda: service._persist_mcp_turn_state,
                _release_session_message_lock=lambda: service._release_session_message_lock,
                _resolved_mcp_tools=lambda: service._resolved_mcp_tools,
                _run_mcp_turn=lambda: service._run_mcp_turn,
                _send_session_message_locked=lambda: service._send_session_message_locked,
                _session_message_lock=lambda: service._session_message_lock,
                _turn_approval=lambda: service._turn_approval,
                agent_log_store=lambda: service.agent_log_store,
                agents=lambda: service.agents,
                call_mcp_tool=lambda: service.call_mcp_tool,
                discover_mcp_tools=lambda: service.discover_mcp_tools,
                mcp_connections=lambda: service.mcp_connections,
                mcp_turn_workers=lambda: service.mcp_turn_workers,
                mcp_turns=lambda: service.mcp_turns,
                mcp_turns_lock=lambda: service.mcp_turns_lock,
                profiles_path=lambda: service.profiles_path,
                router=lambda: service.router,
                run_in_threadpool=lambda: service.run_in_threadpool,
                session_lifecycle_lock=lambda: service.session_lifecycle_lock,
                sessions=lambda: service.sessions,
                task_mcp_approvals=lambda: service.task_mcp_approvals,
                task_mcp_approvals_lock=lambda: service.task_mcp_approvals_lock,
            )
        )

    def __init__(self, bindings: McpServiceBindings) -> None:
        self._bindings = bindings
        service = bindings
        self.discover_connection = make_discover_connection(lambda: service.discover_mcp_tools())
        self.turn_state = McpTurnState(
            lambda: service.sessions(), lambda: service.session_lifecycle_lock()
        )
        self.tool_resolver = McpToolResolver(
            lambda connection_id: service.mcp_connections().get(connection_id),
            lambda: service.run_in_threadpool(),
            lambda: service._discover_connection(),
        )
        self.tool_executor = McpToolExecutor(
            lambda connection_id: service.mcp_connections().get(connection_id),
            lambda connection: service._mcp_header()(connection),
            lambda: service.call_mcp_tool(),
        )
        self.turn_worker = McpTurnWorker(self.worker_runtime)
        self.turn_routes = McpTurnRoutes(self.route_runtime)

    def connection_is_used(self, connection_id: str) -> bool:
        service = self._bindings
        if any(
            access.connection_id == connection_id
            for agent in service.agents().values()
            for access in agent.config.mcp_access
        ):
            return True
        for summary in service.sessions().list():
            session = service.sessions().load(summary.id)
            if session and any(
                access.connection_id == connection_id for access in session.config.mcp_access
            ):
                return True
        return any(
            access.connection_id == connection_id
            for config in ProfilesRepository(service.profiles_path()).load().values()
            for access in config.mcp_access
        )

    def turn_response(self, turn: McpTurnRuntime) -> McpTurnResponse:
        return make_mcp_turn_response(turn)

    def emit_turn(self, turn: McpTurnRuntime, event_type: str, data: dict[str, Any]) -> None:
        self.turn_state.emit(turn, event_type, data)

    def persist_turn_state(
        self,
        session_id: str,
        turn_id: str,
        status_value: str,
        error: str | None = None,
    ) -> None:
        self.turn_state.persist(session_id, turn_id, status_value, error)

    async def resolved_tools(self, config: AgentConfig) -> list[ResolvedMcpTool]:
        return await self.tool_resolver.resolve(config)

    def turn_approval(self, turn: McpTurnRuntime, approval: McpApproval) -> bool:
        return self.turn_state.request_approval(
            turn, approval, self._bindings._persist_mcp_turn_state()
        )

    def execute_resolved_tool(
        self, tool: ResolvedMcpTool, arguments: dict[str, Any]
    ) -> ToolExecutionResult:
        return self.tool_executor.execute(tool, arguments)

    def worker_runtime(self) -> McpTurnWorkerRuntime:
        service = self._bindings
        return McpTurnWorkerRuntime(
            message_lock=service._session_message_lock(),
            release_message_lock=service._release_session_message_lock(),
            threadpool=service.run_in_threadpool(),
            background_factory=BackgroundTasks,
            get_session=service._get_session(),
            resolve_tools=service._resolved_mcp_tools(),
            router=service.router(),
            turn_approval=service._turn_approval(),
            execute_tool=service._execute_resolved_tool(),
            emit_turn=service._emit_turn(),
            send_locked=service._send_session_message_locked(),
            agent_logs=service.agent_log_store(),
            persist_turn=service._persist_mcp_turn_state(),
            turns_lock=service.mcp_turns_lock(),
            workers=service.mcp_turn_workers(),
            sanitize_error=sanitize_error,
        )

    def route_runtime(self) -> McpTurnRouteRuntime:
        service = self._bindings
        return McpTurnRouteRuntime(
            get_session=service._get_session(),
            threadpool=service.run_in_threadpool(),
            persist_turn=service._persist_mcp_turn_state(),
            emit_turn=service._emit_turn(),
            run_turn=service._run_mcp_turn(),
            turns=service.mcp_turns(),
            turns_lock=service.mcp_turns_lock(),
            workers=service.mcp_turn_workers(),
            task_approvals=service.task_mcp_approvals(),
            task_approvals_lock=service.task_mcp_approvals_lock(),
        )
