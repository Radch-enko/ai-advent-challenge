from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from copia.agents.data.profiles_repository import ProfilesRepository
from copia.daily_journal.data.daily_journal_repository import DailyJournalRepository
from copia.daily_journal.domain.errors import DailyJournalStorageError


def test_daily_journal_profile_loads_prompt_from_feature_resource() -> None:
    profile = ProfilesRepository(Path("profiles.json")).load()["daily_journal"]

    assert profile.model == "copia-daily-journal-q4"
    assert "Ты ведёшь ежедневную заметку" in (profile.system_prompt or "")


def test_profile_prompt_resource_rejects_arbitrary_paths(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles.json"
    profiles.write_text(
        json.dumps(
            {
                "journal": {
                    "name": "Journal",
                    "provider": "ollama",
                    "model": "test-model",
                    "system_prompt_resource": "../../private.md",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid system prompt resource"):
        ProfilesRepository(profiles).load()


def test_repository_rejects_unexpected_markdown_heading(tmp_path: Path) -> None:
    repository = DailyJournalRepository(tmp_path)
    path = tmp_path / "2026-10-11.md"
    path.write_text(
        "# 2026-10-11\n\n"
        "## Главное за день\n\n"
        "### Unexpected heading\n\n"
        "## Заметки\n\n"
        "## Идеи и наблюдения\n\n"
        "## Что сделать дальше\n\n"
        "- [ ]\n\n"
        "## Благодарность или итог\n",
        encoding="utf-8",
    )

    with pytest.raises(DailyJournalStorageError):
        repository.read(date(2026, 10, 11))


def test_repository_rejects_symlink_journal_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_root = tmp_path / "Journal"
    linked_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(DailyJournalStorageError):
        DailyJournalRepository(linked_root).read(date(2026, 10, 11))
