from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from copia.mcp.api.mappers.mcp_turn_response import make_mcp_turn_response
from copia.mcp.api.mcp_turn_route_runtime import McpTurnRouteRuntime
from copia.mcp.api.models.mcp_approval_decision import McpApprovalDecision
from copia.mcp.api.models.mcp_turn_response import McpTurnResponse
from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime
from copia.sessions.api.models.message_request import MessageRequest


class McpTurnRoutes:
    def __init__(self, get_runtime: Callable[[], McpTurnRouteRuntime]) -> None:
        self._get_runtime = get_runtime

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/turns",
            self.start_mcp_turn,
            methods=["POST"],
            response_model=McpTurnResponse,
            status_code=202,
        )
        router.add_api_route(
            "/sessions/{session_id}/turns/{turn_id}",
            self.get_mcp_turn,
            methods=["GET"],
            response_model=McpTurnResponse,
        )
        router.add_api_route(
            "/sessions/{session_id}/turns/{turn_id}/events",
            self.stream_mcp_turn_events,
            methods=["GET"],
        )
        router.add_api_route(
            "/sessions/{session_id}/mcp-approvals/{approval_id}",
            self.decide_mcp_approval,
            methods=["POST"],
        )
        return router

    async def start_mcp_turn(self, session_id: str, request: MessageRequest) -> McpTurnResponse:
        runtime = self._get_runtime()
        session = await runtime.get_session(session_id)
        config = (
            request.config
            if request.config is not None and session.profile_name is None
            else session.config
        )
        if not config.mcp_access:
            raise HTTPException(
                409, detail={"code": "mcp_not_enabled", "message": "Agent has no MCP tools enabled"}
            )
        with runtime.turns_lock:
            if any(
                item.session_id == session_id and item.status in {"running", "waiting_for_approval"}
                for item in runtime.turns.values()
            ):
                raise HTTPException(
                    409,
                    detail={
                        "code": "turn_active",
                        "message": "Another turn is active for this session",
                    },
                )
            turn = McpTurnRuntime(id=str(uuid.uuid4()), session_id=session_id)
            runtime.turns[turn.id] = turn
        await runtime.threadpool(runtime.persist_turn, session_id, turn.id, "running", None)
        runtime.emit_turn(turn, "turn_started", {"turn_id": turn.id})
        worker = asyncio.create_task(runtime.run_turn(turn, request))
        with runtime.turns_lock:
            runtime.workers[turn.id] = worker
        return make_mcp_turn_response(turn)

    def require_turn(self, session_id: str, turn_id: str) -> McpTurnRuntime:
        runtime = self._get_runtime()
        with runtime.turns_lock:
            turn = runtime.turns.get(turn_id)
        if turn is None or turn.session_id != session_id:
            raise HTTPException(404, detail={"code": "turn_not_found", "message": "Turn not found"})
        return turn

    async def get_mcp_turn(self, session_id: str, turn_id: str) -> McpTurnResponse:
        return make_mcp_turn_response(self.require_turn(session_id, turn_id))

    async def stream_mcp_turn_events(
        self, session_id: str, turn_id: str, request: Request
    ) -> StreamingResponse:
        turn = self.require_turn(session_id, turn_id)

        async def events():
            index = 0
            while True:
                if await request.is_disconnected():
                    return
                with turn.lock:
                    pending = list(turn.events[index:])
                    terminal = turn.status in {"completed", "failed"}
                for event in pending:
                    index += 1
                    yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                if terminal and index >= len(turn.events):
                    return
                await asyncio.sleep(0.1)

        return StreamingResponse(events(), media_type="text/event-stream")

    async def decide_mcp_approval(
        self, session_id: str, approval_id: str, request: McpApprovalDecision
    ) -> dict[str, Any]:
        runtime = self._get_runtime()
        with runtime.turns_lock:
            turn = next(
                (
                    item
                    for item in runtime.turns.values()
                    if item.session_id == session_id
                    and item.approval is not None
                    and item.approval.id == approval_id
                ),
                None,
            )
        if turn is not None:
            with turn.lock:
                if turn.decision is not None:
                    raise HTTPException(
                        409,
                        detail={
                            "code": "approval_decided",
                            "message": "Approval was already decided",
                        },
                    )
                turn.decision = request.decision == "approve"
                turn.decision_event.set()
            return {"status": "accepted", "turn_id": turn.id}
        with runtime.task_approvals_lock:
            task_runtime = runtime.task_approvals.get(approval_id)
            if task_runtime is not None and task_runtime.session_id == session_id:
                if task_runtime.decision is not None:
                    raise HTTPException(
                        409,
                        detail={
                            "code": "approval_decided",
                            "message": "Approval was already decided",
                        },
                    )
                task_runtime.decision = request.decision == "approve"
                task_runtime.event.set()
                return {"status": "accepted", "task_id": task_runtime.task_id}
        raise HTTPException(
            404, detail={"code": "approval_not_found", "message": "Approval not found"}
        )
