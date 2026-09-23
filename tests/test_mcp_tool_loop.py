from __future__ import annotations

from copia.domain.models.config import (
    AgentConfig,
    ChatMessage,
    LLMResponse,
    ProviderName,
    ToolCall,
    ToolDefinition,
)
from copia.domain.services.mcp_tool_loop import (
    MAX_TOOL_CALLS_PER_TURN,
    McpToolLoop,
    McpToolLoopError,
    ResolvedMcpTool,
    ToolExecutionResult,
    provider_tool_alias,
)


def tool() -> ResolvedMcpTool:
    alias = provider_tool_alias("finances", "add expense / unsafe name")
    return ResolvedMcpTool(
        alias=alias,
        connection_id="finances",
        connection_name="Finances",
        tool_name="add expense / unsafe name",
        definition=ToolDefinition(name=alias, parameters={"type": "object"}),
    )


def config() -> AgentConfig:
    return AgentConfig(name="Agent", provider="openai", model="model")


def test_alias_is_stable_and_provider_safe() -> None:
    alias = provider_tool_alias("finances", "add expense / unsafe name")

    assert alias == provider_tool_alias("finances", "add expense / unsafe name")
    assert len(alias) <= 64
    assert all(character.isalnum() or character in "_-" for character in alias)


def test_approved_tool_result_is_returned_to_provider() -> None:
    selected = tool()

    class Router:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, request_config, tools):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    provider=ProviderName.OPENAI,
                    model="model",
                    tool_calls=[
                        ToolCall(id="call", name=selected.alias, arguments={"amount": 100})
                    ],
                )
            assert messages[-1].content == '{"saved":true}'
            return LLMResponse(content="Saved", provider=ProviderName.OPENAI, model="model")

    executed = []
    loop = McpToolLoop(
        Router(),  # type: ignore[arg-type]
        [selected],
        request_approval=lambda approval: True,
        execute=lambda resolved, arguments: (
            executed.append((resolved.tool_name, arguments))
            or ToolExecutionResult('{"saved":true}')
        ),
        emit=lambda event, data: None,
    )

    response = loop.complete([ChatMessage(role="user", content="save")], config())

    assert response.content == "Saved"
    assert executed == [(selected.tool_name, {"amount": 100})]


def test_rejected_tool_is_not_executed_and_model_continues() -> None:
    selected = tool()

    class Router:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, request_config, tools):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    provider=ProviderName.OPENAI,
                    model="model",
                    tool_calls=[ToolCall(id="call", name=selected.alias, arguments={})],
                )
            assert messages[-1].content == "User rejected this tool call"
            return LLMResponse(content="Cancelled", provider=ProviderName.OPENAI, model="model")

    loop = McpToolLoop(
        Router(),  # type: ignore[arg-type]
        [selected],
        request_approval=lambda approval: False,
        execute=lambda resolved, arguments: (_ for _ in ()).throw(AssertionError()),
        emit=lambda event, data: None,
    )

    assert (
        loop.complete([ChatMessage(role="user", content="save")], config()).content == "Cancelled"
    )


def test_tool_loop_is_bounded() -> None:
    selected = tool()

    class Router:
        def complete(self, messages, request_config, tools):
            return LLMResponse(
                content="",
                provider=ProviderName.OPENAI,
                model="model",
                tool_calls=[ToolCall(id=str(len(messages)), name=selected.alias, arguments={})],
            )

    loop = McpToolLoop(
        Router(),  # type: ignore[arg-type]
        [selected],
        request_approval=lambda approval: False,
        execute=lambda resolved, arguments: ToolExecutionResult("unused"),
        emit=lambda event, data: None,
    )

    try:
        loop.complete([ChatMessage(role="user", content="loop")], config())
    except McpToolLoopError as error:
        assert str(error) == "MCP tool call limit exceeded"
    else:
        raise AssertionError("Expected bounded tool loop failure")
    assert MAX_TOOL_CALLS_PER_TURN == 8
