from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from copia.providers.domain.models.provider_name import ProviderName


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
    started_at: datetime
    finished_at: datetime | None = None
    provider: ProviderName | None = None
    model: str | None = None
    usage: dict[str, int] | None = None

    @field_validator("scheduled_at", "period_from", "period_to", "started_at", "finished_at")
    @classmethod
    def aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Scheduled timestamps must include a timezone")
        return value.astimezone(UTC)
