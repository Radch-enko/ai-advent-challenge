from __future__ import annotations

from types import ModuleType
from typing import Any, Self

from fastapi import BackgroundTasks

from copia.agents.data.profiles_repository import ProfilesRepository
from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.api.artifact_routes import McpArtifactRoutes
from copia.mcp.api.discovery import make_discover_connection
from copia.mcp.api.models.mcp_service_bindings import McpServiceBindings
from copia.mcp.application.mcp_conversation_worker import McpConversationWorker
from copia.mcp.application.mcp_conversation_worker_runtime import McpConversationWorkerRuntime
from copia.mcp.application.mcp_tool_resolver import McpToolResolver
from copia.mcp.data.mcp_tool_executor import McpToolExecutor
from copia.mcp.domain.models.mcp_artifact import McpArtifact
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.providers.application.collect_streamed_response import collect_streamed_response
from copia.security.domain.services.credential_sanitizer import sanitize_error


def _stream_mcp_completion(router, messages, config, emit_delta, tools):
    return collect_streamed_response(
        router,
        messages,
        config,
        lambda _event, data: emit_delta(str(data.get("text", ""))),
        tools,
    )


class McpServiceComposition:
    @classmethod
    def from_service(cls, service: ModuleType) -> Self:
        return cls(
            McpServiceBindings(
                _discover_connection=lambda: service._discover_connection,
                _execute_resolved_tool=lambda: service._execute_resolved_tool,
                _get_session=lambda: service._get_session,
                _mcp_header=lambda: service._mcp_header,
                _release_session_message_lock=lambda: service._release_session_message_lock,
                _resolved_mcp_tools=lambda: service._resolved_mcp_tools,
                _send_session_message_locked=lambda: service._send_session_message_locked,
                _session_message_lock=lambda: service._session_message_lock,
                artifact_store=lambda: service.mcp_artifact_store,
                agents=lambda: service.agents,
                call_mcp_tool=lambda: service.call_mcp_tool,
                discover_mcp_tools=lambda: service.discover_mcp_tools,
                mcp_connections=lambda: service.mcp_connections,
                profiles_path=lambda: service.profiles_path,
                router=lambda: service.router,
                run_in_threadpool=lambda: service.run_in_threadpool,
                sessions=lambda: service.sessions,
            )
        )

    def __init__(self, bindings: McpServiceBindings) -> None:
        self._bindings = bindings
        service = bindings
        self.discover_connection = make_discover_connection(lambda: service.discover_mcp_tools())
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
        self.conversation_worker = McpConversationWorker(self.worker_runtime)
        self.artifact_routes = McpArtifactRoutes(lambda: service.artifact_store())

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

    async def resolved_tools(self, config: AgentConfig) -> list[ResolvedMcpTool]:
        return await self.tool_resolver.resolve(config)

    def execute_resolved_tool(
        self, tool: ResolvedMcpTool, arguments: dict[str, Any]
    ) -> ToolExecutionResult:
        return self.tool_executor.execute(tool, arguments)

    def worker_runtime(self) -> McpConversationWorkerRuntime:
        service = self._bindings
        return McpConversationWorkerRuntime(
            message_lock=service._session_message_lock(),
            release_message_lock=service._release_session_message_lock(),
            threadpool=service.run_in_threadpool(),
            background_factory=BackgroundTasks,
            get_session=service._get_session(),
            resolve_tools=service._resolved_mcp_tools(),
            router=service.router(),
            execute_tool=service._execute_resolved_tool(),
            publish_artifacts=self.publish_artifacts,
            finalize_response=self.finalize_response,
            send_locked=service._send_session_message_locked(),
            sanitize_error=sanitize_error,
            stream_completion=_stream_mcp_completion,
        )

    def finalize_response(
        self, session_id: str, response: Any, artifacts: tuple[McpArtifact, ...]
    ) -> Any:
        return response

    def publish_artifacts(
        self, session_id: str, artifacts: tuple[McpArtifact, ...]
    ) -> tuple[str, ...]:
        references = []
        for artifact in artifacts:
            stored = self._bindings.artifact_store().save(session_id, artifact)
            references.append(f"/api/sessions/{session_id}/artifacts/{stored.artifact_id}")
        return tuple(references)
