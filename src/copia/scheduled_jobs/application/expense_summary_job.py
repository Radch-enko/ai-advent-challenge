import asyncio
from collections.abc import Callable
from datetime import datetime

from copia.agent_logs.domain.services.agent_log_context import agent_log_turn
from copia.mcp.domain.services.mcp_tool_loop import McpToolLoop
from copia.scheduled_jobs.application.expense_summary_pager import ExpenseSummaryPager
from copia.scheduled_jobs.application.expense_summary_runtime import ExpenseSummaryRuntime
from copia.scheduled_jobs.application.scheduled_job_failure import ScheduledJobFailure
from copia.scheduled_jobs.domain.models.scheduled_job import ScheduledJob
from copia.scheduled_jobs.domain.services.expense_summary_prompt import (
    expense_report_timezone,
    expense_summary_config,
    expense_summary_prompt,
)
from copia.scheduled_jobs.domain.services.scheduled_report import humanize_report_datetimes


class ExpenseSummaryJob:
    def __init__(self, get_runtime: Callable[[], ExpenseSummaryRuntime]) -> None:
        self._get_runtime = get_runtime

    def run(self, job: ScheduledJob, period_from: datetime, period_to: datetime) -> tuple[str, str]:
        runtime = self._get_runtime()
        report_timezone = expense_report_timezone(job)
        if job.profile != "accountant":
            raise RuntimeError("Expense summary requires the accountant profile")
        profile = runtime.get_profile(job.profile)
        if profile is None:
            raise RuntimeError(f"Scheduled profile {job.profile} is unavailable")
        allowed = [
            access for access in profile.mcp_access if "search_expenses" in access.enabled_tools
        ]
        if len(allowed) != 1:
            raise RuntimeError("Scheduled profile must have exactly one search_expenses connection")
        config = expense_summary_config(profile, allowed[0].connection_id, report_timezone)
        tools = asyncio.run(runtime.resolve_tools(config))
        if len(tools) != 1 or tools[0].tool_name != "search_expenses":
            raise RuntimeError("Expense search MCP tool is unavailable")

        pager = ExpenseSummaryPager(period_from, period_to, runtime.execute_tool)
        audits: list[dict[str, object]] = []
        loop = McpToolLoop(
            runtime.router,
            tools,
            request_approval=lambda _approval: True,
            execute=pager.execute,
            emit=lambda _event, _data: None,
            audit=audits.append,
            prepare_arguments=pager.prepare,
            max_tool_calls=100,
        )
        session_id = f"scheduled-{job.id}"
        log_id = runtime.agent_logs.start_turn(session_id)
        prompt = expense_summary_prompt(job, period_from, period_to, report_timezone)
        try:
            agent = runtime.make_agent(config, runtime.router, session_id=session_id)
            with agent_log_turn(session_id, log_id, provider=config.provider, model=config.model):
                response = agent.ask(prompt, agent_log_id=log_id, completion=loop.complete)
            if not pager.called or not pager.finished:
                raise RuntimeError("Agent did not read every expense page")
            if not response.content.strip():
                raise RuntimeError("Agent returned an empty summary")
            for entry in audits:
                runtime.agent_logs.append_tool_call(log_id, entry)
            runtime.finish_log(
                log_id,
                provider=response.provider,
                model=response.model,
                usage=response.usage,
                status="completed",
            )
            return humanize_report_datetimes(response.content.strip(), report_timezone), log_id
        except Exception as error:
            for entry in audits:
                runtime.agent_logs.append_tool_call(log_id, entry)
            runtime.finish_log(log_id, status="failed", error=runtime.sanitize_error(str(error)))
            raise ScheduledJobFailure(runtime.sanitize_error(str(error)), log_id) from error
