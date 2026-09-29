from __future__ import annotations

from types import ModuleType
from typing import Any, Self

from fastapi import HTTPException

from copia.conversations.api.conversation_route_runtime import ConversationRouteRuntime
from copia.conversations.api.models.conversation_command import (
    ApprovalDecisionCommand,
    CompletionCommand,
    ConversationCommand,
    RetrySummarizationCommand,
    SendMessageCommand,
)
from copia.conversations.application.conversation_run import ConversationRun
from copia.conversations.application.conversation_service import (
    ConversationOperations,
    ConversationService,
)
from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.providers.api.models.completion_request import CompletionRequest
from copia.providers.application.collect_streamed_response import collect_streamed_response
from copia.sessions.api.models.message_request import MessageRequest


class ConversationServiceComposition:
    @classmethod
    def from_service(cls, service: ModuleType) -> Self:
        return cls(service)

    def __init__(self, service: ModuleType) -> None:
        self._service = service
        self.conversation_service = ConversationService(
            ConversationOperations(
                message=self._message,
                completion=self._completion,
                retry_summarization=self._retry_summarization,
            )
        )

    def route_runtime(self) -> ConversationRouteRuntime:
        return ConversationRouteRuntime(
            store=self._service.conversation_store,
            validate=self._validate,
            execute=self.conversation_service.execute,
            decide_approval=self._decide_approval,
        )

    async def _validate(self, command: ConversationCommand) -> None:
        service = self._service
        if isinstance(command, SendMessageCommand):
            if command.target.kind == "session":
                await service.session_message_routes.validate_streaming_message(command.target.id)
                return
            agent = service.agents.get(command.target.id)
            if agent is None:
                raise HTTPException(status_code=404, detail={"code": "agent_not_found"})
            if agent.config.mcp_access:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "agent_mcp_not_supported",
                        "message": "MCP tools require a session",
                    },
                )
        elif isinstance(command, RetrySummarizationCommand):
            await service._get_session(command.session_id)
        elif isinstance(command, ApprovalDecisionCommand):
            await service._get_session(command.session_id)
            run = service.conversation_store.find_pending_approval(
                command.session_id, command.approval_id
            )
            with service.task_mcp_approvals_lock:
                task_approval = service.task_mcp_approvals.get(command.approval_id)
            if run is None and (
                task_approval is None or task_approval.session_id != command.session_id
            ):
                raise HTTPException(status_code=404, detail={"code": "approval_not_found"})
            if run is not None and run.decision is not None:
                raise HTTPException(status_code=409, detail={"code": "approval_decided"})
            if task_approval is not None and task_approval.decision is not None:
                raise HTTPException(status_code=409, detail={"code": "approval_decided"})

    @staticmethod
    def _emit_tool_event(run: ConversationRun, event_type: str, data: dict[str, object]) -> None:
        if event_type == "tool_approval_required":
            run.prepare_approval(McpApproval.model_validate(data))
            run.emit("tool.approval_required", data)
        elif event_type == "tool_running":
            run.emit(
                "tool.running",
                {key: data[key] for key in ("tool_name", "decision") if key in data},
            )
        elif event_type == "tool_completed":
            run.emit(
                "tool.completed",
                {
                    key: data[key]
                    for key in ("tool_name", "status", "duration_seconds")
                    if key in data
                },
            )
        elif event_type == "message.delta":
            run.emit("message.delta", data)

    async def _message(
        self,
        run: ConversationRun,
        command: SendMessageCommand,
        emit,
    ) -> Any:
        service = self._service
        if command.target.kind == "agent":
            return await service.agent_routes.execute_streaming_message(
                command.target.id, MessageRequest(content=command.content), emit
            )

        session = await service._get_session(command.target.id)
        config = (
            command.config
            if command.config is not None and session.profile_name is None
            else session.config
        )
        request = MessageRequest(content=command.content, config=command.config)
        if not config.mcp_access:
            return await service.session_message_routes.execute_streaming_message(
                command.target.id, request, emit
            )

        if not service.conversation_store.claim_session(run.id, session.id):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "conversation_active",
                    "message": "A conversation is already active for this session",
                },
            )
        try:
            return await service.mcp_conversation_worker.run(
                run,
                request,
                emit=lambda name, data: self._emit_tool_event(run, name, data),
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=502,
                detail={"code": "mcp_execution_failed", "message": "MCP execution failed"},
            ) from error
        finally:
            service.conversation_store.release_session(run.id)

    async def _completion(
        self,
        _run: ConversationRun,
        command: CompletionCommand,
        emit,
    ) -> Any:
        request = CompletionRequest(config=command.config, messages=command.messages)
        return await self._service.provider_routes.execute_streaming_completion(request, emit)

    async def _retry_summarization(
        self,
        _run: ConversationRun,
        command: RetrySummarizationCommand,
        emit,
    ) -> Any:
        service = self._service

        def completion(messages, config):
            return collect_streamed_response(service.router, messages, config, emit)

        return await service.session_message_routes.retry_session_summarization(
            command.session_id, completion=completion
        )

    async def _decide_approval(
        self, session_id: str, approval_id: str, decision: str
    ) -> dict[str, object]:
        service = self._service
        run = service.conversation_store.find_pending_approval(session_id, approval_id)
        if run is not None:
            try:
                if run.decide_approval(approval_id, decision == "approve"):
                    return {"status": "accepted", "conversation_id": run.id}
            except ValueError as error:
                raise HTTPException(status_code=409, detail={"code": "approval_decided"}) from error
        with service.task_mcp_approvals_lock:
            runtime = service.task_mcp_approvals.get(approval_id)
            if runtime is not None and runtime.session_id == session_id:
                if runtime.decision is not None:
                    raise HTTPException(status_code=409, detail={"code": "approval_decided"})
                runtime.decision = decision == "approve"
                runtime.event.set()
                return {"status": "accepted", "task_id": runtime.task_id}
        raise HTTPException(status_code=404, detail={"code": "approval_not_found"})
