from pydantic import BaseModel, ConfigDict, Field

from copia.scheduled_jobs.domain.models.report_period_spec import ReportPeriodSpec
from copia.scheduled_jobs.domain.models.schedule_spec import ScheduleSpec


class ScheduledJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: str
    profile: str = "accountant"
    enabled: bool = True
    schedule: ScheduleSpec
    report_period: ReportPeriodSpec = Field(default_factory=ReportPeriodSpec)
