from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from copia.api import service
from copia.api.scheduled_runner import ScheduledRunner
from copia.data.agent_log_store import AgentLogStore
from copia.data.scheduled_runs_repository import ScheduledRunsRepository
from copia.domain.models.config import LLMResponse, ToolCall, ToolDefinition
from copia.domain.models.scheduled_job import ScheduledJob
from copia.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult


def test_job_statuses_and_next_run_are_visible_in_api(monkeypatch, tmp_path) -> None:
    job = ScheduledJob(
        id="summary",
        name="Минутная сводка",
        kind="expense_summary",
        schedule={"type": "interval", "minutes": 1},
    )
    config = tmp_path / "schedules.json"
    config.write_text(json.dumps({"jobs": [job.model_dump(mode="json")]}))
    clock = [datetime(2026, 9, 1, 8, tzinfo=UTC)]
    started = threading.Event()
    release = threading.Event()

    def handle(_job, _start, _end):
        started.set()
        release.wait(timeout=3)
        return "**Готово**", "log-id"

    runner = ScheduledRunner(
        config,
        tmp_path / "state.json",
        ScheduledRunsRepository(tmp_path / "runs"),
        {"expense_summary": handle},
        now=lambda: clock[0],
    )
    runner.start()
    monkeypatch.setattr(service, "scheduled_runner", runner)
    try:
        client = TestClient(service.app)
        waiting = client.get("/scheduled-jobs/status").json()
        assert waiting[0]["name"] == "Минутная сводка"
        assert waiting[0]["status"] == "wait"
        assert datetime.fromisoformat(waiting[0]["next_run_at"]).tzinfo is not None

        clock[0] += timedelta(minutes=1)
        worker = threading.Thread(target=runner.run_due, args=(job.id,))
        worker.start()
        assert started.wait(timeout=3)
        assert client.get("/scheduled-jobs/status").json()[0]["status"] == "progress"
        release.set()
        worker.join(timeout=3)
        assert not worker.is_alive()
        assert client.get("/scheduled-jobs/status").json()[0]["status"] == "completed"
    finally:
        release.set()
        runner.shutdown()


def test_summary_agent_uses_one_way_report_instruction(monkeypatch):
    tool = ResolvedMcpTool(
        alias="search",
        connection_id="finances",
        connection_name="Finances",
        tool_name="search_expenses",
        definition=ToolDefinition(name="search", parameters={"type": "object"}),
    )

    async def resolve(_config):
        return [tool]

    monkeypatch.setattr(service, "_resolved_mcp_tools", resolve)
    monkeypatch.setattr(service, "agent_log_store", AgentLogStore())
    monkeypatch.setattr(
        service,
        "_execute_resolved_tool",
        lambda _tool, _args: ToolExecutionResult(
            json.dumps({"structured_content": {"items": [], "next_cursor": None}})
        ),
    )

    class Router:
        def complete(self, messages, config, tools):
            assert "one-way expense report" in config.system_prompt
            assert "Do not address the user as in a chat" in config.system_prompt
            assert "offer to continue" in config.system_prompt
            assert len(tools) == 1
            if not any(message.role == "tool" for message in messages):
                assert "без возможности продолжить беседу" in messages[-1].content
                return LLMResponse(
                    content="",
                    provider="openai",
                    model="fake",
                    tool_calls=[ToolCall(id="1", name="search", arguments={})],
                )
            return LLMResponse(
                content="**Ваши расходы за последний час:** расходов нет.",
                provider="openai",
                model="fake",
            )

    monkeypatch.setattr(service, "router", Router())
    job = ScheduledJob(
        id="summary", kind="expense_summary", schedule={"type": "interval", "minutes": 60}
    )
    start = datetime(2026, 9, 1, 8, tzinfo=UTC)
    answer, _log_id = service._expense_summary_job(job, start, start + timedelta(hours=1))
    assert answer == "**Ваши расходы за последний час:** расходов нет."


def test_one_minute_schedule_uses_natural_period_label() -> None:
    job = ScheduledJob(
        id="summary", kind="expense_summary", schedule={"type": "interval", "minutes": 1}
    )
    assert service._expense_period_label(job) == "последнюю минуту"
