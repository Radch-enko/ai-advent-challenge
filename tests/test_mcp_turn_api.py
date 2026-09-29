from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from threading import Thread

from fastapi.testclient import TestClient

from copia import service
from copia.agents.domain.models.agent_config import AgentConfig
from copia.conversations.api.models.conversation_command import SendMessageCommand
from copia.conversations.application.conversation_store import ConversationStore
from copia.mcp.domain.models.mcp_access_config import McpAccessConfig
from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.llm_stream_event import LLMStreamEvent
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.tool_call import ToolCall
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_state import TaskState


def test_legacy_message_turn_and_approval_routes_are_removed() -> None:
    client = TestClient(service.app)
    assert client.post("/sessions/session/messages", json={"content": "search"}).status_code == 404
    assert client.post("/sessions/session/turns", json={}).status_code == 404
    assert client.get("/sessions/session/turns/turn/events").status_code == 404
    assert client.post("/sessions/session/mcp-approvals/a", json={}).status_code == 404


def test_approval_command_resumes_pending_conversation(monkeypatch) -> None:
    store = ConversationStore()
    monkeypatch.setattr(service, "conversation_store", store)
    turn, _ = store.create("mcp-request", {"command": "message"})
    turn.session_id = "session"
    turn.prepare_approval(
        McpApproval(
            id="approval",
            connection_id="finances",
            connection_name="Finances",
            tool_name="search",
            arguments={"category": "food"},
        )
    )
    asyncio.run(service.conversation_composition._decide_approval("session", "approval", "approve"))

    assert turn.decision is True
    assert turn.decision_event.is_set()


def test_removed_turn_event_route_does_not_replay() -> None:
    response = TestClient(service.app).get("/sessions/session/turns/turn/events")
    assert response.status_code == 404


def test_mcp_conversation_waits_for_approval_executes_and_finishes(monkeypatch, tmp_path) -> None:
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

    def stream(messages, config, tools=None):
        yield LLMStreamEvent(kind="completed", response=complete(messages, config, tools))

    monkeypatch.setattr(service.router, "stream", stream)

    store = ConversationStore()
    monkeypatch.setattr(service, "conversation_store", store)
    conversation, _ = store.create("mcp-session-request", {"command": "message"})
    command = SendMessageCommand(
        command="message",
        request_id="mcp-session-request",
        target={"kind": "session", "id": "session"},
        content="search",
    )

    async def exercise():
        worker = asyncio.create_task(service.conversation_service.execute(conversation, command))
        for _ in range(100):
            if conversation.approval is not None:
                break
            await asyncio.sleep(0.01)
        assert conversation.approval is not None
        conversation.decide_approval(conversation.approval.id, True)
        await worker
        return conversation

    conversation = asyncio.run(exercise())

    assert conversation.status == "completed"
    assert [event["event"] for event in conversation.events] == [
        "conversation.started",
        "message.started",
        "tool.approval_required",
        "tool.running",
        "tool.completed",
        "conversation.completed",
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


def test_interrupted_conversation_is_persisted_as_terminal_failure(tmp_path) -> None:
    path = tmp_path / "conversations.sqlite3"
    first_store = ConversationStore(path)
    run, _ = first_store.create("lost-request", {"command": "message"})
    run.emit("message.delta", {"text": "partial"})

    recovered = ConversationStore(path).get(run.id)

    assert recovered is not None
    assert recovered.status == "failed"
    assert recovered.events[-1]["event"] == "conversation.failed"
    assert recovered.events[-1]["data"]["code"] == "interrupted_by_restart"
