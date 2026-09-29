from datetime import datetime

from copia.agents.domain.models.agent_config import AgentConfig
from copia.common.domain.services.prompt_resources import render_prompt
from copia.mcp.domain.models.mcp_access_config import McpAccessConfig
from copia.scheduled_jobs.domain.models.scheduled_job import ScheduledJob
from copia.scheduled_jobs.domain.services.scheduled_report import human_datetime


def expense_period_label(job: ScheduledJob) -> str:
    if job.report_period.type == "current_day":
        return "сегодняшний день"
    schedule = job.schedule
    if schedule.type == "calendar":
        return "неделю" if schedule.day_of_week else "день"
    assert schedule.minutes is not None
    if schedule.minutes == 1:
        return "последнюю минуту"
    if schedule.minutes == 60:
        return "последний час"
    if schedule.minutes % 60 == 0:
        return f"последние {schedule.minutes // 60} ч"
    return f"последние {schedule.minutes} мин"


def expense_report_timezone(job: ScheduledJob) -> str:
    return job.report_period.timezone or job.schedule.timezone or "UTC"


def expense_summary_config(profile: AgentConfig, connection_id: str, timezone: str) -> AgentConfig:
    return profile.model_copy(
        update={
            "system_prompt": render_prompt(
                "copia.scheduled_jobs", "expense_summary_system.md", timezone=timezone
            ),
            "mcp_access": [
                McpAccessConfig(connection_id=connection_id, enabled_tools=["search_expenses"])
            ],
            "context_management": profile.context_management.model_copy(update={"enabled": False}),
        }
    )


def expense_summary_prompt(
    job: ScheduledJob, period_from: datetime, period_to: datetime, timezone: str
) -> str:
    period_label = expense_period_label(job)
    return render_prompt(
        "copia.scheduled_jobs",
        "expense_summary_request.md",
        period_label=period_label,
        timezone=timezone,
        period_from=human_datetime(period_from, timezone),
        period_to=human_datetime(period_to, timezone),
    )
