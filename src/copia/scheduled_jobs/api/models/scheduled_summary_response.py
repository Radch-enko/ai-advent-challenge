from __future__ import annotations

from pydantic import BaseModel

from copia.scheduled_jobs.domain.models.scheduled_run import ScheduledRun


class ScheduledSummaryResponse(BaseModel):
    job_id: str | None
    latest_run: ScheduledRun | None
    published_run: ScheduledRun | None
