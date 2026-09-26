from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from copia.scheduled_jobs.domain.models.scheduled_job import ScheduledJob


def trigger_for(job: ScheduledJob, activated_at: datetime):
    spec = job.schedule
    if spec.type == "interval":
        assert spec.minutes is not None
        return IntervalTrigger(
            minutes=spec.minutes,
            start_date=activated_at + timedelta(minutes=spec.minutes),
            timezone=UTC,
        )
    assert spec.time is not None and spec.timezone is not None
    hour, minute = map(int, spec.time.split(":"))
    return CronTrigger(
        hour=hour,
        minute=minute,
        day_of_week=spec.day_of_week,
        timezone=ZoneInfo(spec.timezone),
    )


def previous_fire(job: ScheduledJob, activated_at: datetime, at: datetime) -> datetime | None:
    if job.schedule.type == "interval":
        assert job.schedule.minutes is not None
        delta = timedelta(minutes=job.schedule.minutes)
        count = (at - activated_at) // delta
        return activated_at + count * delta if count >= 1 else None
    lookback = timedelta(days=8 if job.schedule.day_of_week else 2)
    trigger = trigger_for(job, activated_at)
    cursor = at - lookback
    latest = None
    while True:
        next_fire = trigger.get_next_fire_time(latest, cursor)
        if next_fire is None or next_fire.astimezone(UTC) > at:
            value = latest.astimezone(UTC) if latest else None
            return value if value is not None and value > activated_at else None
        latest = next_fire
        cursor = next_fire


def preceding_fire(job: ScheduledJob, activated_at: datetime, current: datetime) -> datetime:
    if job.schedule.type == "interval":
        assert job.schedule.minutes is not None
        return current - timedelta(minutes=job.schedule.minutes)
    previous = previous_fire(job, current - timedelta(days=16), current - timedelta(microseconds=1))
    if previous is None:
        raise ValueError("Could not calculate previous calendar fire time")
    return previous


def report_window(
    job: ScheduledJob, activated_at: datetime, scheduled_at: datetime, execution_at: datetime
) -> tuple[datetime, datetime]:
    if job.report_period.type == "scheduled_interval":
        return preceding_fire(job, activated_at, scheduled_at), scheduled_at
    assert job.report_period.timezone is not None
    local_now = execution_at.astimezone(ZoneInfo(job.report_period.timezone))
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    end = max(execution_at.astimezone(UTC), start + timedelta(microseconds=1))
    return start, end
