from __future__ import annotations

from datetime import datetime
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
