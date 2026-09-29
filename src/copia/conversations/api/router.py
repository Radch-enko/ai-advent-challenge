from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from copia.conversations.api.conversation_route_runtime import ConversationRouteRuntime
from copia.conversations.api.models.conversation_command import (
    ApprovalDecisionCommand,
    ConversationCommand,
    ResumeConversationCommand,
    SendMessageCommand,
)
from copia.conversations.application.conversation_store import (
    ConversationConflictError,
)
from copia.conversations.data.conversation_repository import ConversationStorageLimitError


def create_conversation_router(
    get_runtime: Callable[[], ConversationRouteRuntime],
) -> APIRouter:
    router = APIRouter()

    async def conversation(request: Request, command: ConversationCommand) -> StreamingResponse:
        runtime = get_runtime()
        if isinstance(command, ResumeConversationCommand):
            run = runtime.store.get(command.conversation_id) if command.conversation_id else None
            if run is None:
                run = runtime.store.get_by_request_id(command.request_id)
            if run is None:
                raise HTTPException(
                    status_code=410, detail={"code": "conversation_replay_unavailable"}
                )
            try:
                index = runtime.store.event_index(run, command.after_event_id)
            except ValueError as error:
                raise HTTPException(
                    status_code=422, detail={"code": "invalid_event_cursor"}
                ) from error
            return _stream_response(run, index, request)

        if isinstance(command, ApprovalDecisionCommand):
            request_fingerprint = command.model_dump(
                mode="json", exclude={"request_id", "after_event_id"}
            )
            try:
                existing = runtime.store.find_request(command.request_id, request_fingerprint)
            except ConversationConflictError as error:
                raise HTTPException(
                    status_code=409, detail={"code": "request_id_conflict"}
                ) from error
            except ConversationStorageLimitError as error:
                raise HTTPException(
                    status_code=503, detail={"code": "conversation_storage_full"}
                ) from error
            if existing is not None:
                return _stream_response(existing, 0, request)
            try:
                await runtime.validate(command)
                run, created = runtime.store.create(
                    command.request_id,
                    request_fingerprint,
                )
            except ConversationConflictError as error:
                raise HTTPException(
                    status_code=409, detail={"code": "request_id_conflict"}
                ) from error
            except ConversationStorageLimitError as error:
                raise HTTPException(
                    status_code=503, detail={"code": "conversation_storage_full"}
                ) from error
            except HTTPException:
                raise
            except Exception as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "approval_not_found"},
                ) from error
            if created and run.status == "running":
                asyncio.create_task(_execute_approval(runtime, run, command))
            return _stream_response(run, 0, request)

        request_fingerprint = command.model_dump(mode="json", exclude={"request_id"})
        try:
            existing = runtime.store.find_request(command.request_id, request_fingerprint)
        except ConversationConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "request_id_conflict"},
            ) from error
        except ConversationStorageLimitError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "conversation_storage_full"},
            ) from error
        if existing is not None:
            return _stream_response(existing, 0, request)
        await runtime.validate(command)
        request_id = command.request_id
        try:
            run, created = runtime.store.create(request_id, request_fingerprint)
        except ConversationConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "request_id_conflict"},
            ) from error
        except ConversationStorageLimitError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "conversation_storage_full"},
            ) from error
        if created and run.status == "running":
            if isinstance(command, SendMessageCommand) and command.target.kind == "session":
                run.session_id = command.target.id
            asyncio.create_task(runtime.execute(run, command))
        return _stream_response(run, 0, request)

    router.add_api_route("/conversation", conversation, methods=["POST"])
    return router


async def _execute_approval(
    runtime: ConversationRouteRuntime,
    run,
    command: ApprovalDecisionCommand,
) -> None:
    try:
        await runtime.decide_approval(command.session_id, command.approval_id, command.decision)
        run.emit(
            "approval.accepted", {"approval_id": command.approval_id, "decision": command.decision}
        )
        run.emit("conversation.completed", {"conversation_id": run.id})
    except Exception:
        run.emit(
            "conversation.failed",
            {
                "conversation_id": run.id,
                "code": "approval_decision_failed",
                "message": "Approval decision could not be applied",
            },
        )


def _stream_response(run, index: int, request: Request) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        cursor = index
        while True:
            if await request.is_disconnected():
                return
            pending = await asyncio.to_thread(run.wait_for_events, cursor, 10.0)
            if not pending:
                if run.status in {"completed", "failed"}:
                    return
                yield ": keep-alive\n\n"
                continue
            for event in pending:
                cursor += 1
                yield (
                    f"id: {event['id']}\n"
                    f"event: {event['event']}\n"
                    f"data: {json.dumps(event['data'], ensure_ascii=False, separators=(',', ':'))}\n\n"
                )
                if event["event"] in {"conversation.completed", "conversation.failed"}:
                    return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
