from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


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
