from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copia.daily_journal.api.router import create_daily_journal_router
from copia.daily_journal.data import daily_journal_repository
from copia.daily_journal.data.daily_journal_repository import DailyJournalRepository
from copia.daily_journal.domain.errors import (
    DailyJournalConflictError,
    DailyJournalStorageError,
)
from copia.daily_journal.domain.models.daily_journal_change import (
    DailyJournalChange,
    DailyJournalOperation,
    DailyJournalSection,
)

NOTE_DATE = date(2026, 10, 11)


def add_change(section: DailyJournalSection, text: str) -> DailyJournalChange:
    return DailyJournalChange(
        operation=DailyJournalOperation.ADD,
        section=section,
        text=text,
    )


def test_read_missing_note_returns_exact_template_without_creating_file(tmp_path: Path) -> None:
    repository = DailyJournalRepository(tmp_path)

    result = repository.read(NOTE_DATE)

    assert result.exists is False
    assert result.revision is None
    assert result.content == (
        "# 2026-10-11\n\n"
        "## Главное за день\n\n"
        "## Заметки\n\n"
        "## Идеи и наблюдения\n\n"
        "## Что сделать дальше\n\n"
        "- [ ]\n\n"
        "## Благодарность или итог\n"
    )
    assert not (tmp_path / "2026-10-11.md").exists()


def test_apply_creates_note_and_duplicate_add_is_idempotent(tmp_path: Path) -> None:
    repository = DailyJournalRepository(tmp_path)
    change = add_change(DailyJournalSection.MAIN, "Собрал демонстрационный прототип")

    first = repository.apply(NOTE_DATE, expected_revision=None, changes=[change])
    second = repository.apply(NOTE_DATE, expected_revision=None, changes=[change])

    assert first.changed is True
    assert second.changed is False
    assert second.content.count("- Собрал демонстрационный прототип") == 1
    assert (tmp_path / "2026-10-11.md").read_text(encoding="utf-8") == first.content


def test_apply_preserves_other_sections_and_supports_replacing_and_completing_tasks(
    tmp_path: Path,
) -> None:
    repository = DailyJournalRepository(tmp_path)
    initial = repository.apply(
        NOTE_DATE,
        expected_revision=None,
        changes=[
            add_change(DailyJournalSection.NOTES, "Обсудили макет экрана"),
            add_change(DailyJournalSection.NEXT_STEPS, "Отправить макет коллеге"),
        ],
    )
    changes = [
        DailyJournalChange(
            operation=DailyJournalOperation.REPLACE,
            section=DailyJournalSection.NOTES,
            previous_text="Обсудили макет экрана",
            text="Согласовали макет экрана",
        ),
        DailyJournalChange(
            operation=DailyJournalOperation.COMPLETE_TASK,
            section=DailyJournalSection.NEXT_STEPS,
            text="Отправить макет коллеге",
        ),
    ]

    updated = repository.apply(NOTE_DATE, expected_revision=initial.revision, changes=changes)

    assert "- Обсудили макет экрана" not in updated.content
    assert "- Согласовали макет экрана" in updated.content
    assert "- [x] Отправить макет коллеге" in updated.content
    assert updated.content.count("## ") == 5


def test_stale_revision_conflicts_without_overwriting_existing_note(tmp_path: Path) -> None:
    repository = DailyJournalRepository(tmp_path)
    first = repository.apply(
        NOTE_DATE,
        expected_revision=None,
        changes=[add_change(DailyJournalSection.MAIN, "Первое событие")],
    )
    repository.apply(
        NOTE_DATE,
        expected_revision=first.revision,
        changes=[add_change(DailyJournalSection.NOTES, "Вторая запись")],
    )
    before_conflict = repository.read(NOTE_DATE)

    with pytest.raises(DailyJournalConflictError):
        repository.apply(
            NOTE_DATE,
            expected_revision=first.revision,
            changes=[add_change(DailyJournalSection.IDEAS, "Новая идея")],
        )

    assert repository.read(NOTE_DATE).content == before_conflict.content


def test_non_append_edit_requires_read_revision(tmp_path: Path) -> None:
    repository = DailyJournalRepository(tmp_path)
    repository.apply(
        NOTE_DATE,
        expected_revision=None,
        changes=[add_change(DailyJournalSection.MAIN, "Демонстрационное событие")],
    )
    replace_change = DailyJournalChange(
        operation=DailyJournalOperation.REPLACE,
        section=DailyJournalSection.MAIN,
        previous_text="Демонстрационное событие",
        text="Исправленное событие",
    )

    with pytest.raises(DailyJournalConflictError):
        repository.apply(NOTE_DATE, expected_revision=None, changes=[replace_change])


def test_symlink_note_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("private demonstration data", encoding="utf-8")
    (tmp_path / "2026-10-11.md").symlink_to(outside)
    repository = DailyJournalRepository(tmp_path)

    with pytest.raises(DailyJournalStorageError):
        repository.read(NOTE_DATE)


def test_failed_atomic_replace_keeps_previous_note(tmp_path: Path, monkeypatch) -> None:
    repository = DailyJournalRepository(tmp_path)
    original = repository.apply(
        NOTE_DATE,
        expected_revision=None,
        changes=[add_change(DailyJournalSection.MAIN, "Прежняя запись")],
    )

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(daily_journal_repository.os, "replace", fail_replace)
    with pytest.raises(DailyJournalStorageError):
        repository.apply(
            NOTE_DATE,
            expected_revision=original.revision,
            changes=[add_change(DailyJournalSection.NOTES, "Новая запись")],
        )

    assert repository.read(NOTE_DATE).content == original.content
    assert list(tmp_path.glob(".daily-journal-*.tmp")) == []


def test_http_api_reads_updates_and_reports_revision_conflicts(tmp_path: Path) -> None:
    app = FastAPI()
    repository = DailyJournalRepository(tmp_path)
    app.include_router(create_daily_journal_router(lambda: repository))
    client = TestClient(app)

    missing = client.get("/daily-journal/2026-10-11")
    created = client.patch(
        "/daily-journal/2026-10-11",
        json={
            "expected_revision": None,
            "changes": [
                {
                    "operation": "add",
                    "section": "main",
                    "text": "Проверил тестовый сценарий",
                }
            ],
        },
    )
    stale = client.patch(
        "/daily-journal/2026-10-11",
        json={
            "expected_revision": "0" * 64,
            "changes": [
                {
                    "operation": "add",
                    "section": "ideas",
                    "text": "Не добавлять при конфликте",
                }
            ],
        },
    )

    assert missing.status_code == 200
    assert missing.json()["exists"] is False
    assert created.status_code == 200
    assert "- Проверил тестовый сценарий" in created.json()["content"]
    assert stale.status_code == 409
    assert "Не добавлять при конфликте" not in repository.read(NOTE_DATE).content


def test_http_api_rejects_invalid_dates_and_multiline_entries(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_daily_journal_router(lambda: DailyJournalRepository(tmp_path)))
    client = TestClient(app)

    invalid_date = client.get("/daily-journal/../../outside")
    multiline = client.patch(
        "/daily-journal/2026-10-11",
        json={
            "expected_revision": None,
            "changes": [
                {
                    "operation": "add",
                    "section": "notes",
                    "text": "first line\n## injected heading",
                }
            ],
        },
    )

    assert invalid_date.status_code in {404, 422}
    assert multiline.status_code == 422
