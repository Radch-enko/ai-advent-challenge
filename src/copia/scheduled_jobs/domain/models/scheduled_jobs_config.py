from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from copia.scheduled_jobs.domain.models.scheduled_job import ScheduledJob


class ScheduledJobsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: list[ScheduledJob] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> ScheduledJobsConfig:
        ids = [job.id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("Scheduled job IDs must be unique")
        return self
