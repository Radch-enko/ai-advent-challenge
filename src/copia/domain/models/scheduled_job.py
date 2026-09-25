from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScheduleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["interval", "calendar"]
    minutes: int | None = Field(default=None, ge=1)
    day_of_week: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] | None = None
    time: str | None = None
    timezone: str | None = None

    @field_validator("time")
    @classmethod
    def valid_time(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                parsed = datetime.strptime(value, "%H:%M")
            except ValueError as error:
                raise ValueError("time must use HH:MM") from error
            if parsed.strftime("%H:%M") != value:
                raise ValueError("time must use HH:MM")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError as error:
                raise ValueError("Unknown timezone") from error
        return value

    @model_validator(mode="after")
    def valid_combination(self) -> ScheduleSpec:
        if self.type == "interval":
            if self.minutes is None or any(
                value is not None for value in (self.day_of_week, self.time, self.timezone)
            ):
                raise ValueError("Interval schedule requires only minutes")
        elif self.minutes is not None or self.time is None or self.timezone is None:
            raise ValueError("Calendar schedule requires time and timezone")
        return self


class ReportPeriodSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["scheduled_interval", "current_day"] = "scheduled_interval"
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError as error:
                raise ValueError("Unknown report timezone") from error
        return value

    @model_validator(mode="after")
    def valid_combination(self) -> ReportPeriodSpec:
        if self.type == "current_day" and self.timezone is None:
            raise ValueError("Current-day report requires a timezone")
        if self.type == "scheduled_interval" and self.timezone is not None:
            raise ValueError("Scheduled-interval report does not use a timezone")
        return self


class ScheduledJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: str
    profile: str = "accountant"
    enabled: bool = True
    schedule: ScheduleSpec
    report_period: ReportPeriodSpec = Field(default_factory=ReportPeriodSpec)


class ScheduledJobsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: list[ScheduledJob] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> ScheduledJobsConfig:
        ids = [job.id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("Scheduled job IDs must be unique")
        return self


class ScheduledRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    kind: str
    scheduled_at: datetime
    period_from: datetime
    period_to: datetime
    status: Literal["running", "completed", "failed"]
    answer: str | None = None
    error: str | None = None
    agent_log_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    @field_validator("scheduled_at", "period_from", "period_to", "started_at", "finished_at")
    @classmethod
    def aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Scheduled timestamps must include a timezone")
        return value.astimezone(UTC)
