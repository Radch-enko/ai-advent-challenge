from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from copia import service
from copia.mcp.data.mcp_artifact_store import McpArtifactStore
from copia.mcp.data.mcp_tool_executor import McpToolExecutor
from copia.mcp.domain.models.mcp_artifact import McpArtifact
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.services.mcp_tool_loop import (
    McpToolLoop,
    ResolvedMcpTool,
    ToolExecutionResult,
    provider_tool_alias,
)
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.tool_call import ToolCall
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.sessions.domain.models.chat_message import ChatMessage


def connection() -> McpConnection:
    return McpConnection(
        id="finances",
        name="Finances",
        endpoint="https://example.test/mcp",
        updated_at=datetime.now(UTC),
    )


def test_executor_extracts_png_and_keeps_non_image_result_for_model() -> None:
    image_data = b"png-bytes"

    async def call_tool(endpoint, tool_name, arguments, **options):
        from copia.mcp.domain.models.mcp_call_result import McpCallResult

        return McpCallResult(
            content=[
                {
                    "type": "image",
                    "data": base64.b64encode(image_data).decode(),
                    "mimeType": "image/png",
                },
                {"type": "text", "text": "chart created"},
            ],
            structured_content={"filename": "expense-comparison.png"},
        )

    tool = ResolvedMcpTool(
        alias="alias",
        connection_id="finances",
        connection_name="Finances",
        tool_name="save_expense_chart",
        definition=ToolDefinition(name="alias", parameters={"type": "object"}),
    )
    executor = McpToolExecutor(
        lambda connection_id: connection() if connection_id == "finances" else None,
        lambda _connection: (None, None),
        lambda: call_tool,
    )

    result = executor.execute(tool, {})

    assert result.artifacts == (
        McpArtifact(data=image_data, mime_type="image/png", filename="expense-comparison.png"),
    )
    payload = json.loads(result.content)
    assert payload["content"] == [{"type": "text", "text": "chart created"}]


def test_artifact_store_is_session_scoped(tmp_path) -> None:
    store = McpArtifactStore(tmp_path / "artifacts")
    stored = store.save(
        "session-a",
        McpArtifact(data=b"png", mime_type="image/png", filename="chart.png"),
    )

    assert store.path("session-a", stored.artifact_id) is not None
    assert store.path("session-b", stored.artifact_id) is None
    assert store.path("../outside", stored.artifact_id) is None


def test_artifact_endpoint_serves_png_and_rejects_unknown_artifact(monkeypatch, tmp_path) -> None:
    store = McpArtifactStore(tmp_path / "artifacts")
    stored = store.save(
        "session-a",
        McpArtifact(data=b"png", mime_type="image/png", filename="chart.png"),
    )
    monkeypatch.setattr(service, "mcp_artifact_store", store)

    client = TestClient(service.app)
    response = client.get(f"/sessions/session-a/artifacts/{stored.artifact_id}")
    missing = client.get("/sessions/session-a/artifacts/missing")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"png"
    assert missing.status_code == 404


def test_tool_loop_finalizer_runs_after_image_tool() -> None:
    alias = provider_tool_alias("finances", "save_expense_chart")
    selected = ResolvedMcpTool(
        alias=alias,
        connection_id="finances",
        connection_name="Finances",
        tool_name="save_expense_chart",
        definition=ToolDefinition(name=alias, parameters={"type": "object"}),
    )

    class Router:
        calls = 0

        def complete(self, messages, config, tools):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    provider=ProviderName.OPENAI,
                    model="model",
                    tool_calls=[ToolCall(id="chart", name=alias, arguments={})],
                )
            return LLMResponse(content="Done", provider=ProviderName.OPENAI, model="model")

    finalized: list[tuple[str, int]] = []
    loop = McpToolLoop(
        Router(),
        [selected],
        request_approval=lambda _approval: True,
        execute=lambda _tool, _arguments: ToolExecutionResult(
            content='{"created":true}',
            artifacts=(McpArtifact(b"png", "image/png", "chart.png"),),
        ),
        emit=lambda _event, _data: None,
        finalize=lambda response, artifacts: (
            finalized.append((response.content, len(artifacts)))
            or response.model_copy(update={"content": response.content + "\n\n![chart](/image)"})
        ),
    )

    response = loop.complete(
        [ChatMessage(role="user", content="compare")],
        LLMConfig(provider=ProviderName.OPENAI, model="model"),
    )

    assert response.content == "Done\n\n![chart](/image)"
    assert finalized == [("Done", 1)]
