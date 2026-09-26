from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from copia import service
from copia.scheduled_jobs.application.schedule_timing import report_window
from copia.scheduled_jobs.application.scheduled_runner import ScheduledRunner
from copia.scheduled_jobs.data.scheduled_runs_repository import ScheduledRunsRepository
from copia.scheduled_jobs.domain.models.scheduled_job import ScheduledJob


def current_day_job() -> ScheduledJob:
    return ScheduledJob(
        id="expense-summary-daily",
        kind="expense_summary",
        schedule={"type": "interval", "minutes": 1},
        report_period={"type": "current_day", "timezone": "Asia/Omsk"},
    )


def test_current_day_window_is_cumulative_and_resets_at_local_midnight() -> None:
    job = current_day_job()
    activated = datetime(2026, 9, 1, 17, 58, tzinfo=UTC)
    before_midnight = datetime(2026, 9, 1, 17, 59, 30, tzinfo=UTC)
    after_midnight = datetime(2026, 9, 1, 18, 1, 30, tzinfo=UTC)

    assert report_window(job, activated, before_midnight, before_midnight) == (
        datetime(2026, 8, 31, 18, tzinfo=UTC),
        before_midnight,
    )
    assert report_window(job, activated, after_midnight, after_midnight) == (
        datetime(2026, 9, 1, 18, tzinfo=UTC),
        after_midnight,
    )
    assert service._expense_period_label(job) == "сегодняшний день"


def test_minute_schedule_reports_today_instead_of_last_minute(tmp_path) -> None:
    job = current_day_job()
    config = tmp_path / "schedules.json"
    config.write_text(json.dumps({"jobs": [job.model_dump(mode="json")]}))
    clock = [datetime(2026, 9, 1, 18, 10, 30, tzinfo=UTC)]
    windows: list[tuple[datetime, datetime]] = []

    def handle(_job, start, end):
        windows.append((start, end))
        return "Ваши расходы за сегодняшний день", "log-id"

    runner = ScheduledRunner(
        config,
        tmp_path / "state.json",
        ScheduledRunsRepository(tmp_path / "runs"),
        {"expense_summary": handle},
        now=lambda: clock[0],
    )
    runner.start()
    try:
        clock[0] += timedelta(minutes=1)
        first = runner.run_due(job.id)
        clock[0] += timedelta(minutes=1)
        second = runner.run_due(job.id)
    finally:
        runner.shutdown()

    midnight = datetime(2026, 9, 1, 18, tzinfo=UTC)
    assert windows == [
        (midnight, datetime(2026, 9, 1, 18, 11, 30, tzinfo=UTC)),
        (midnight, datetime(2026, 9, 1, 18, 12, 30, tzinfo=UTC)),
    ]
    assert first.scheduled_at != first.period_from
    assert second.period_from == first.period_from
    assert second.period_to > first.period_to


def test_current_day_requires_explicit_report_timezone() -> None:
    with pytest.raises(ValidationError, match="requires a timezone"):
        ScheduledJob(
            id="summary",
            kind="expense_summary",
            schedule={"type": "interval", "minutes": 1},
            report_period={"type": "current_day"},
        )
