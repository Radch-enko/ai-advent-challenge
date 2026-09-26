from __future__ import annotations

import json
from datetime import UTC, datetime

from copia import service
from copia.agent_logs.data.agent_log_store import AgentLogStore
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, ToolExecutionResult
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.tool_call import ToolCall
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.scheduled_jobs.domain.models.scheduled_job import ScheduledJob
from copia.scheduled_jobs.domain.services.scheduled_report import humanize_report_datetimes


def day_job() -> ScheduledJob:
    return ScheduledJob(
        id="summary",
        kind="expense_summary",
        schedule={"type": "interval", "minutes": 1},
        report_period={"type": "current_day", "timezone": "Asia/Omsk"},
    )


def install_expense_tool(monkeypatch) -> None:
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
            json.dumps(
                {
                    "structured_content": {
                        "items": [
                            {
                                "id": "aca78d53-f239-4301-b21e-3241ce32fa9b",
                                "occurred_at": "2026-09-25T13:03:00+06:00",
                                "name": "Поездка на такси",
                                "amount_rub": "250",
                            }
                        ],
                        "next_cursor": None,
                    },
                    "is_error": False,
                },
                ensure_ascii=False,
            )
        ),
    )


def test_false_empty_report_is_published_without_a_correction_call(monkeypatch):
    install_expense_tool(monkeypatch)

    class Router:
        calls = 0

        def complete(self, messages, config, tools):
            self.calls += 1
            assert "never expose ISO 8601" in config.system_prompt
            if self.calls == 1:
                assert "25 сентября 2026 года" in messages[-1].content
                assert "2026-09-25T" not in messages[-1].content
                return LLMResponse(
                    content="",
                    provider="openai",
                    model="fake",
                    tool_calls=[ToolCall(id="1", name="search", arguments={})],
                )
            assert self.calls == 2
            assert '"expense_count":1' in messages[-1].content
            assert "Поездка на такси" in messages[-1].content
            return LLMResponse(
                content="Ваши расходы за сегодняшний день отсутствуют.",
                provider="openai",
                model="fake",
            )

    router = Router()
    monkeypatch.setattr(service, "router", router)
    start = datetime(2026, 9, 24, 18, tzinfo=UTC)
    end = datetime(2026, 9, 25, 7, 28, tzinfo=UTC)
    answer, _log_id = service._expense_summary_job(day_job(), start, end)

    assert router.calls == 2
    assert answer == "Ваши расходы за сегодняшний день отсутствуют."


def test_nonempty_report_dates_are_humanized(monkeypatch):
    install_expense_tool(monkeypatch)

    class Router:
        calls = 0

        def complete(self, _messages, _config, _tools):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    provider="openai",
                    model="fake",
                    tool_calls=[ToolCall(id="1", name="search", arguments={})],
                )
            return LLMResponse(
                content="Ваши расходы за сегодняшний день: такси — 250 ₽, 2026-09-25T07:03:00+00:00.",
                provider="openai",
                model="fake",
            )

    router = Router()
    monkeypatch.setattr(service, "router", router)
    start = datetime(2026, 9, 24, 18, tzinfo=UTC)
    end = datetime(2026, 9, 25, 7, 28, tzinfo=UTC)
    answer, _log_id = service._expense_summary_job(day_job(), start, end)

    assert router.calls == 2
    assert "такси — 250 ₽" in answer
    assert "25 сентября 2026 года, 13:03" in answer
    assert "2026-09-25T" not in answer


def test_report_date_format() -> None:
    assert (
        humanize_report_datetimes(
            "С 2026-09-24T18:00:00+00:00 до 2026-09-25T07:28:18.087985+00:00",
            "Asia/Omsk",
        )
        == "С 25 сентября 2026 года, 00:00 до 25 сентября 2026 года, 13:28"
    )
