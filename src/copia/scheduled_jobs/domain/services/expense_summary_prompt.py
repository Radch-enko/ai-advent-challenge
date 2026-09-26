from datetime import datetime

from copia.agents.domain.models.agent_config import AgentConfig
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
            "system_prompt": (
                "You are the accountant producing a scheduled, one-way expense report. "
                "Use only expenses returned by search_expenses for the specified period. "
                "Report only facts present in the expense records; do not infer trip durations "
                "or add other details that the records do not contain. "
                "Write a concise factual report in Russian. Markdown headings and lists are allowed. "
                f"Render dates in natural Russian using the {timezone} timezone; "
                "never expose ISO 8601 timestamps or raw UTC offsets in the report. "
                "Do not address the user as in a chat, ask questions, offer to continue, "
                "propose follow-up work, or add general advice or next steps. "
                "End immediately after the report. If the period has no expenses, state that plainly."
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
    return (
        f"Подготовь сводку расходов за {expense_period_label(job)}. "
        f"Период по {timezone}: с {human_datetime(period_from, timezone)} "
        f"до {human_datetime(period_to, timezone)}. "
        "Точные границы запроса задаёт backend. "
        "Обязательно вызови search_expenses и прочитай все страницы до next_cursor=null. "
        "Смотри на expense_count и structured_content.items в ответе инструмента; "
        "если expense_count больше нуля, обязательно опиши найденные расходы. "
        "Указывай только сведения из записей расходов; не придумывай длительность поездок "
        "или другие отсутствующие детали. "
        "Если расходов нет, скажи об этом. Начни ответ словами «Ваши расходы за "
        f"{expense_period_label(job)}». Не выдумывай расходы. "
        "Даты в ответе пиши по-русски, например «25 сентября 2026 года, 13:03»; "
        "не выводи даты в ISO 8601 или UTC. "
        "Это автоматический отчёт без возможности продолжить беседу: "
        "не задавай вопросов и не предлагай дальнейшие действия."
    )
