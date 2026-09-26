from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from copia import service
from copia.agent_logs.data.agent_log_repository import JsonAgentLogRepository
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.tool_call import ToolCall
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.scheduled_jobs.application.schedule_timing import preceding_fire, previous_fire
from copia.scheduled_jobs.application.scheduled_job_failure import ScheduledJobFailure
from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner
from copia.scheduled_jobs.data.scheduled_runs_repository import ScheduledRunsRepository
from copia.scheduled_jobs.domain.models.scheduled_job import ScheduledJob
from copia.scheduled_jobs.domain.models.scheduled_run import ScheduledRun


def hourly_job() -> ScheduledJob:
    return ScheduledJob(
        id="summary", kind="expense_summary", schedule={"type": "interval", "minutes": 60}
    )


def weekly_job() -> ScheduledJob:
    return ScheduledJob(
        id="weekly",
        kind="expense_summary",
        schedule={
            "type": "calendar",
            "day_of_week": "mon",
            "time": "09:00",
            "timezone": "Asia/Omsk",
        },
    )


def test_schedule_windows_and_timezone() -> None:
    activation = datetime(2026, 9, 1, 6, tzinfo=UTC)
    hourly = previous_fire(hourly_job(), activation, datetime(2026, 9, 1, 9, 30, tzinfo=UTC))
    assert hourly == datetime(2026, 9, 1, 9, tzinfo=UTC)
    assert preceding_fire(hourly_job(), activation, hourly) == datetime(2026, 9, 1, 8, tzinfo=UTC)
    weekly = previous_fire(weekly_job(), activation, datetime(2026, 9, 15, tzinfo=UTC))
    assert weekly == datetime(2026, 9, 14, 3, tzinfo=UTC)
    assert preceding_fire(weekly_job(), activation, weekly) == datetime(2026, 9, 7, 3, tzinfo=UTC)


def test_runner_catches_up_once_and_recovers_interrupted_run(tmp_path) -> None:
    config = tmp_path / "schedules.json"
    config.write_text(json.dumps({"jobs": [hourly_job().model_dump(mode="json")]}))
    runs = ScheduledRunsRepository(tmp_path / "runs")
    state = tmp_path / "state.json"
    clock = [datetime(2026, 9, 1, 6, tzinfo=UTC)]
    calls = []
    runner = ScheduledRunner(
        config,
        state,
        runs,
        {
            "expense_summary": lambda job, start, end: (
                calls.append((start, end)) or "Сводка",
                "log-id",
            )
        },
        now=lambda: clock[0],
    )
    runner.start()
    runner.shutdown()
    clock[0] += timedelta(hours=4, minutes=5)
    restored = ScheduledRunner(
        config,
        state,
        runs,
        runner.handlers,
        now=lambda: clock[0],
    )
    restored.start()
    result = restored.run_due("summary")
    restored.shutdown()
    assert result is not None and result.status == "completed"
    assert result.period_from == datetime(2026, 9, 1, 9, tzinfo=UTC)
    assert result.period_to == datetime(2026, 9, 1, 10, tzinfo=UTC)
    assert restored.run_due("summary") is None
    assert len(calls) == 1
    interrupted = result.model_copy(
        update={"status": "running", "answer": None, "finished_at": None}
    )
    runs.save(interrupted)
    runs.fail_interrupted("summary")
    assert runs.latest("summary").status == "failed"
    assert runs.latest("summary").error == "Backend stopped during this run"


@pytest.mark.parametrize("pages,expected_success", [(0, False), (1, True), (2, True)])
def test_agent_mcp_summary_bounds_and_pagination(monkeypatch, tmp_path, pages, expected_success):
    tool = ResolvedMcpTool(
        alias="mcp_finances_search",
        connection_id="finances",
        connection_name="Finances",
        tool_name="search_expenses",
        definition=ToolDefinition(name="mcp_finances_search", parameters={"type": "object"}),
    )

    async def resolve(config):
        assert [access.enabled_tools for access in config.mcp_access] == [["search_expenses"]]
        return [tool]

    monkeypatch.setattr(service, "_resolved_mcp_tools", resolve)
    monkeypatch.setattr(
        service,
        "agent_log_store",
        AgentLogStore(repository=JsonAgentLogRepository(tmp_path / "sessions")),
    )
    seen = []

    def execute(_tool, arguments):
        seen.append(arguments)
        cursor = "page-2" if pages == 2 and len(seen) == 1 else None
        return ToolExecutionResult(
            json.dumps(
                {"structured_content": {"items": [], "next_cursor": cursor}, "is_error": False}
            )
        )

    monkeypatch.setattr(service, "_execute_resolved_tool", execute)

    class Router:
        def complete(self, messages, _config, tools):
            if not tools:
                raise AssertionError("Expected MCP tool definition")
            if pages == 0:
                return LLMResponse(content="invented", provider="openai", model="fake")
            tool_results = [message for message in messages if message.role == "tool"]
            if len(tool_results) < pages:
                args = {"occurred_from": "1900-01-01T00:00:00Z", "page_size": 1}
                if tool_results:
                    args["cursor"] = "page-2"
                return LLMResponse(
                    content="",
                    provider="openai",
                    model="fake",
                    tool_calls=[
                        ToolCall(id=str(len(tool_results)), name=tool.alias, arguments=args)
                    ],
                )
            assert "structured_content" in tool_results[-1].content
            return LLMResponse(
                content="Ваши расходы за последний час: 0 ₽", provider="openai", model="fake"
            )

    monkeypatch.setattr(service, "router", Router())
    start = datetime(2026, 9, 1, 8, tzinfo=UTC)
    end = start + timedelta(hours=1)
    if expected_success:
        answer, log_id = service._expense_summary_job(hourly_job(), start, end)
        assert answer == "Ваши расходы за последний час: 0 ₽"
        log = service.agent_log_store.get_turn("scheduled-summary", log_id)
        assert [entry["arguments"] for entry in log.tool_calls] == seen
    else:
        with pytest.raises(ScheduledJobFailure, match="did not read"):
            service._expense_summary_job(hourly_job(), start, end)
    assert len(seen) == pages
    for index, args in enumerate(seen):
        assert args["occurred_from"] == start.isoformat()
        assert args["occurred_to"] == (end - timedelta(microseconds=1)).isoformat()
        assert args["page_size"] == 100
        assert args.get("cursor") == ("page-2" if index else None)


@pytest.mark.parametrize("failure", ["mcp_error", "missing_page"])
def test_agent_rejects_mcp_error_or_unread_page(monkeypatch, tmp_path, failure):
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
    monkeypatch.setattr(
        service,
        "agent_log_store",
        AgentLogStore(repository=JsonAgentLogRepository(tmp_path / "sessions")),
    )
    monkeypatch.setattr(
        service,
        "_execute_resolved_tool",
        lambda _tool, _args: ToolExecutionResult(
            json.dumps(
                {"structured_content": {"items": [], "next_cursor": "next"}, "is_error": False}
            ),
            is_error=failure == "mcp_error",
        ),
    )

    class Router:
        def complete(self, messages, _config, tools):
            if not any(message.role == "tool" for message in messages):
                return LLMResponse(
                    content="",
                    provider="openai",
                    model="fake",
                    tool_calls=[ToolCall(id="1", name="search", arguments={})],
                )
            return LLMResponse(content="Partial summary", provider="openai", model="fake")

    monkeypatch.setattr(service, "router", Router())
    start = datetime(2026, 9, 1, 8, tzinfo=UTC)
    with pytest.raises(ScheduledJobFailure) as raised:
        service._expense_summary_job(hourly_job(), start, start + timedelta(hours=1))
    assert raised.value.agent_log_id is not None
    log = service.agent_log_store.get_turn("scheduled-summary", raised.value.agent_log_id)
    assert log.status == "failed"
    assert log.tool_calls[0]["arguments"]["occurred_from"] == start.isoformat()


def test_scheduled_json_redacts_tokens_and_keeps_latest_completed(tmp_path):
    runs = ScheduledRunsRepository(tmp_path / "runs")
    start = datetime(2026, 9, 1, 8, tzinfo=UTC)
    completed = ScheduledRun(
        job_id="summary",
        kind="expense_summary",
        scheduled_at=start + timedelta(hours=1),
        period_from=start,
        period_to=start + timedelta(hours=1),
        status="completed",
        answer="Ваши расходы. token=secret-value",
        started_at=start,
    )
    runs.save(completed)
    failed = completed.model_copy(
        update={
            "scheduled_at": start + timedelta(hours=2),
            "status": "failed",
            "answer": None,
            "error": "Bearer secret-value",
        }
    )
    runs.save(failed)
    assert runs.latest_completed("summary").answer == "Ваши расходы. token=[REDACTED]"
    assert runs.latest("summary").error == "Bearer [REDACTED]"
    assert "secret-value" not in "".join(
        path.read_text() for path in (tmp_path / "runs" / "summary").glob("*.json")
    )


def test_latest_summary_api_keeps_published_answer_after_failed_run(monkeypatch, tmp_path):
    runs = ScheduledRunsRepository(tmp_path / "runs")
    monkeypatch.setattr(service, "scheduled_runs", runs)
    monkeypatch.setattr(service.scheduled_runner, "jobs", {"summary": hourly_job()})
    start = datetime(2026, 9, 1, 8, tzinfo=UTC)
    completed = ScheduledRun(
        job_id="summary",
        kind="expense_summary",
        scheduled_at=start + timedelta(hours=1),
        period_from=start,
        period_to=start + timedelta(hours=1),
        status="completed",
        answer="Ваши расходы за последний час: 0 ₽",
        started_at=start,
    )
    runs.save(completed)
    runs.save(
        completed.model_copy(
            update={
                "scheduled_at": start + timedelta(hours=2),
                "status": "failed",
                "answer": None,
                "error": "MCP unavailable",
            }
        )
    )
    payload = TestClient(service.app).get("/scheduled-summaries/latest").json()
    assert payload["published_run"]["answer"] == "Ваши расходы за последний час: 0 ₽"
    assert payload["latest_run"]["status"] == "failed"


def test_runner_persists_handler_failure_with_log_id(tmp_path):
    config = tmp_path / "schedules.json"
    config.write_text(json.dumps({"jobs": [hourly_job().model_dump(mode="json")]}))
    clock = [datetime(2026, 9, 1, 8, tzinfo=UTC)]

    def fail(_job, _start, _end):
        raise ScheduledJobFailure("Bearer secret-value", "log-id")

    runs = ScheduledRunsRepository(tmp_path / "runs")
    runner = ScheduledRunner(
        config,
        tmp_path / "state.json",
        runs,
        {"expense_summary": fail},
        now=lambda: clock[0],
    )
    runner.start()
    clock[0] += timedelta(hours=1)
    result = runner.run_due("summary")
    runner.shutdown()
    assert result is not None and result.status == "failed"
    stored = runs.latest("summary")
    assert stored.agent_log_id == "log-id"
    assert stored.error == "Bearer [REDACTED]"
    assert stored.answer is None
