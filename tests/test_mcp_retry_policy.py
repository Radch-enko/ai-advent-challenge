from __future__ import annotations

import pytest

from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.domain.services.mcp_tool_loop import (
    McpToolLoop,
    McpToolLoopError,
    ToolExecutionResult,
)
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.domain.models.chat_message import ChatMessage


def test_final_validation_allows_one_correction_retry() -> None:
    class Router:
        calls = 0

        def complete(self, messages, config, tools):
            self.calls += 1
            return LLMResponse(content="draft", provider=ProviderName.OPENAI, model="model")

    router = Router()
    loop = McpToolLoop(
        router,  # type: ignore[arg-type]
        [],
        request_approval=lambda _: True,
        execute=lambda _, __: ToolExecutionResult("unused"),
        emit=lambda _, __: None,
        review_final=lambda _: "correction",
    )

    with pytest.raises(McpToolLoopError, match="MCP final response failed validation"):
        loop.complete(
            [ChatMessage(role="user", content="request")],
            AgentConfig(name="Agent", provider="openai", model="model"),
        )

    assert router.calls == 2
