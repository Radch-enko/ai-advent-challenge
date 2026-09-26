from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from threading import Thread

from fastapi.testclient import TestClient

from copia import service
from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.application.models.mcp_turn_runtime import McpTurnRuntime
from copia.mcp.domain.models.mcp_access_config import McpAccessConfig
from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.tool_call import ToolCall
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.sessions.api.models.message_request import MessageRequest
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_state import TaskState


def test_mcp_enabled_session_requires_async_turn_api(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    monkeypatch.setattr(service, "working_memory", WorkingMemoryRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service, "pending_memory_repository", PendingMemoryRepository(tmp_path / "sessions")
    )
    session = ChatSession(
        id="session",
        config=AgentConfig(
            name="Agent",
            provider="openai",
            model="model",
            mcp_access=[McpAccessConfig(connection_id="finances", enabled_tools=["search"])],
        ),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.save(session)

    response = TestClient(service.app).post(
        "/sessions/session/messages", json={"content": "search"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "mcp_turn_required"


def test_approval_endpoint_resumes_pending_turn() -> None:
    turn = McpTurnRuntime(id="turn", session_id="session")
    turn.approval = McpApproval(
        id="approval",
        connection_id="finances",
        connection_name="Finances",
        tool_name="search",
        arguments={"category": "food"},
    )
    turn.status = "waiting_for_approval"
    with service.mcp_turns_lock:
        service.mcp_turns[turn.id] = turn
    try:
        response = TestClient(service.app).post(
            "/sessions/session/mcp-approvals/approval", json={"decision": "approve"}
        )
    finally:
        with service.mcp_turns_lock:
            service.mcp_turns.pop(turn.id, None)

    assert response.status_code == 200
    assert turn.decision is True
    assert turn.decision_event.is_set()


def test_sse_replays_turn_events() -> None:
    turn = McpTurnRuntime(id="turn", session_id="session", status="completed")
    service._emit_turn(turn, "turn_started", {"turn_id": "turn"})
    service._emit_turn(turn, "final", {"response": {"content": "done"}})
    with service.mcp_turns_lock:
        service.mcp_turns[turn.id] = turn
    try:
        response = TestClient(service.app).get("/sessions/session/turns/turn/events")
    finally:
        with service.mcp_turns_lock:
            service.mcp_turns.pop(turn.id, None)

    assert response.status_code == 200
    assert "event: turn_started" in response.text
    assert "event: final" in response.text


def test_background_turn_waits_for_approval_executes_and_finishes(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    monkeypatch.setattr(service, "working_memory", WorkingMemoryRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service, "pending_memory_repository", PendingMemoryRepository(tmp_path / "sessions")
    )
    session = ChatSession(
        id="session",
        title="Existing",
        config=AgentConfig(
            name="Agent",
            provider="openai",
            model="model",
            mcp_access=[McpAccessConfig(connection_id="finances", enabled_tools=["search"])],
        ),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.save(session)
    alias = "mcp_finances_search"

    async def resolved(config):
        return [
            ResolvedMcpTool(
                alias=alias,
                connection_id="finances",
                connection_name="Finances",
                tool_name="search",
                definition=ToolDefinition(name=alias, parameters={"type": "object"}),
            )
        ]

    monkeypatch.setattr(service, "_resolved_mcp_tools", resolved)
    monkeypatch.setattr(
        service,
        "_execute_resolved_tool",
        lambda tool, arguments: ToolExecutionResult('{"items":[]}'),
    )
    calls = 0

    def complete(messages, config, tools=None):
        nonlocal calls
        if tools is None:
            return LLMResponse(
                content='{"candidates":[]}',
                structured_data={"candidates": []},
                provider=ProviderName.OPENAI,
                model="model",
            )
        calls += 1
        if calls == 1:
            return LLMResponse(
                content="",
                provider=ProviderName.OPENAI,
                model="model",
                tool_calls=[ToolCall(id="approval", name=alias, arguments={})],
            )
        return LLMResponse(content="Done", provider=ProviderName.OPENAI, model="model")

    monkeypatch.setattr(service.router, "complete", complete)

    async def exercise() -> McpTurnRuntime:
        turn = McpTurnRuntime(id="turn", session_id="session")
        worker = asyncio.create_task(service._run_mcp_turn(turn, MessageRequest(content="search")))
        for _ in range(100):
            if turn.approval is not None:
                break
            await asyncio.sleep(0.01)
        assert turn.approval is not None
        turn.decision = True
        turn.decision_event.set()
        await worker
        return turn

    turn = asyncio.run(exercise())

    assert turn.status == "completed"
    assert turn.result is not None
    assert turn.result.response.content == "Done"
    assert [event["type"] for event in turn.events] == [
        "tool_approval_required",
        "tool_running",
        "tool_completed",
        "final",
    ]


def test_task_mode_persists_pending_approval_and_resumes(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    task = TaskState(
        id="task",
        original_instruction="Search expenses",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.save(
        ChatSession(
            id="session",
            title="Existing",
            config=AgentConfig(name="Agent", provider="openai", model="model"),
            task=task,
            tasks=[task],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    approval = McpApproval(
        id="approval",
        connection_id="finances",
        connection_name="Finances",
        tool_name="search",
        arguments={},
    )
    outcome: list[bool] = []
    thread = Thread(
        target=lambda: outcome.append(
            service._request_task_mcp_approval("session", "task", approval)
        )
    )
    thread.start()
    for _ in range(100):
        current = repository.load("session")
        if current and current.task and current.task.mcp_approval is not None:
            break
        __import__("time").sleep(0.01)
    current = repository.load("session")
    assert current is not None and current.task is not None
    assert current.task.mcp_approval == approval
    with service.task_mcp_approvals_lock:
        runtime = service.task_mcp_approvals[approval.id]
        runtime.decision = True
        runtime.event.set()
    thread.join(timeout=1)

    updated = repository.load("session")
    assert outcome == [True]
    assert updated is not None and updated.task is not None
    assert updated.task.mcp_approval is None


def test_interrupted_chat_turn_is_marked_failed_on_load(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    repository.save(
        ChatSession(
            id="session",
            config=AgentConfig(name="Agent", provider="openai", model="model"),
            mcp_turn_id="lost-turn",
            mcp_turn_status="waiting_for_approval",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    loaded = service._get_session_locked("session")

    assert loaded.mcp_turn_status == "failed"
    assert loaded.mcp_turn_error == "interrupted_by_restart"
