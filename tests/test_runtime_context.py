from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone

from copia.agents.domain.models.agent_config import AgentConfig
from copia.common.domain.services.runtime_context import (
    render_current_datetime_context,
    with_current_datetime_context,
)
from copia.mcp.domain.services.mcp_tool_loop import (
    McpToolLoop,
    ResolvedMcpTool,
    ToolExecutionResult,
)
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.tasks.domain.models.task_stage import TaskStage


def test_runtime_context_is_rfc3339_and_replaces_previous_value() -> None:
    first = datetime(2026, 9, 23, 17, 45, 12, tzinfo=timezone(timedelta(hours=6)))
    second = datetime(2026, 9, 23, 17, 46, 13, tzinfo=timezone(timedelta(hours=6)))

    messages = with_current_datetime_context([ChatMessage(role="user", content="Hello")], first)
    updated = with_current_datetime_context(messages, second)

    assert len(updated) == 2
    assert updated[0].role == "system"
    assert "2026-09-23T17:46:13+06:00" in updated[0].content
    assert updated[0].content.count("<current_datetime_context>") == 1
    assert "Timezone: UTC+06:00" in updated[0].content
    assert "UTC offset: +06:00" in updated[0].content
    assert "17:45:12" not in updated[0].content
    assert render_current_datetime_context(first).startswith("<current_datetime_context>")


def test_agent_request_gets_runtime_context_without_persisting_it() -> None:
    from copia.agents.domain.models.agent import Agent

    captured = []

    class Router:
        def complete(self, messages, config):
            captured.append(messages)
            return LLMResponse(content="Done", provider=ProviderName.OPENAI, model="model")

    agent = Agent(AgentConfig(name="Agent", provider="openai", model="model"), Router())  # type: ignore[arg-type]
    agent.ask("What time is it?")

    assert "<current_datetime_context>" in captured[0][0].content
    assert all("<current_datetime_context>" not in message.content for message in agent.history)


def test_mcp_loop_refreshes_runtime_context_for_each_provider_call() -> None:
    selected = ResolvedMcpTool(
        alias="expense_tool",
        connection_id="finances",
        connection_name="Finances",
        tool_name="search_expenses",
        definition=ToolDefinition(name="expense_tool", parameters={"type": "object"}),
    )
    captured = []

    class Router:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, config, tools):
            captured.append(messages[0].content)
            self.calls += 1
            if self.calls == 1:
                from copia.providers.domain.models.tool_call import ToolCall

                return LLMResponse(
                    content="",
                    provider=ProviderName.OPENAI,
                    model="model",
                    tool_calls=[ToolCall(id="call", name="expense_tool", arguments={})],
                )
            return LLMResponse(content="Done", provider=ProviderName.OPENAI, model="model")

    response = McpToolLoop(
        Router(),  # type: ignore[arg-type]
        [selected],
        request_approval=lambda approval: True,
        execute=lambda tool, arguments: ToolExecutionResult("ok"),
        emit=lambda event, data: None,
    ).complete(
        [ChatMessage(role="user", content="Find")],
        AgentConfig(name="Agent", provider="openai", model="model"),
    )

    assert response.content == "Done"
    assert len(captured) == 2
    assert all("<current_datetime_context>" in content for content in captured)


def test_task_complete_call_adds_runtime_context(monkeypatch) -> None:
    from copia import service

    captured = []
    config = AgentConfig(name="Agent", provider="openai", model="model")
    session = ChatSession(
        id="session",
        config=config,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class Router:
        def complete(self, messages, request_config):
            captured.append(messages)
            return LLMResponse(content="Done", provider=ProviderName.OPENAI, model="model")

    async def get_session(session_id):
        return session

    monkeypatch.setattr(service, "router", Router())
    monkeypatch.setattr(service, "_get_session", get_session)
    monkeypatch.setattr(service, "_task_call_start", lambda *args, **kwargs: "log-id")
    monkeypatch.setattr(service, "_task_call_finish", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_finish_agent_log", lambda *args, **kwargs: None)

    response = asyncio.run(
        service._task_complete_call(
            "session",
            "task",
            stage=TaskStage.PLANNING,
            kind="task_planning",
            step_id=None,
            messages=[ChatMessage(role="user", content="Plan")],
            config=config,
        )
    )

    assert response.content == "Done"
    assert "<current_datetime_context>" in captured[0][0].content
