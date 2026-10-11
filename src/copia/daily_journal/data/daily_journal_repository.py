from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from datetime import date
from pathlib import Path

from copia.daily_journal.domain.errors import (
    DailyJournalConflictError,
    DailyJournalStorageError,
)
from copia.daily_journal.domain.models.daily_journal_change import (
    DailyJournalChange,
    DailyJournalOperation,
    DailyJournalSection,
)
from copia.daily_journal.domain.models.daily_journal_note import DailyJournalNote

HEADINGS = (
    (DailyJournalSection.MAIN, "## Главное за день"),
    (DailyJournalSection.NOTES, "## Заметки"),
    (DailyJournalSection.IDEAS, "## Идеи и наблюдения"),
    (DailyJournalSection.NEXT_STEPS, "## Что сделать дальше"),
    (DailyJournalSection.GRATITUDE, "## Благодарность или итог"),
)
_WRITE_LOCK = threading.RLock()


class DailyJournalRepository:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().absolute()

    def read(self, day: date) -> DailyJournalNote:
        path = self._path(day)
        with _WRITE_LOCK:
            if not path.exists():
                return DailyJournalNote(date=day.isoformat(), content=_template(day), exists=False)
            content = self._read_content(path, day)
            return DailyJournalNote(
                date=day.isoformat(),
                content=content,
                revision=_revision(content),
                exists=True,
            )

    def apply(
        self,
        day: date,
        *,
        expected_revision: str | None,
        changes: list[DailyJournalChange],
    ) -> DailyJournalNote:
        path = self._path(day)
        with _WRITE_LOCK:
            exists = path.exists()
            current = self._read_content(path, day) if exists else _template(day)
            current_revision = _revision(current) if exists else None
            append_only = all(change.operation == DailyJournalOperation.ADD for change in changes)
            if expected_revision is None and exists and not append_only:
                raise DailyJournalConflictError(
                    "Read the daily journal note before editing entries"
                )
            if expected_revision is not None and current_revision != expected_revision:
                if _changes_already_applied(current, changes):
                    return DailyJournalNote(
                        date=day.isoformat(),
                        content=current,
                        revision=current_revision,
                        exists=exists,
                    )
                raise DailyJournalConflictError("Daily journal note changed since it was read")

            updated = _apply_changes(current, changes)
            if updated == current and exists:
                return DailyJournalNote(
                    date=day.isoformat(),
                    content=current,
                    revision=current_revision,
                    exists=True,
                )
            self._atomic_write(path, updated)
            return DailyJournalNote(
                date=day.isoformat(),
                content=updated,
                revision=_revision(updated),
                exists=True,
                changed=True,
            )

    def _path(self, day: date) -> Path:
        if not isinstance(day, date):
            raise ValueError("Daily journal date is invalid")
        current = self._root
        while current != current.parent:
            if current.is_symlink():
                raise DailyJournalStorageError(
                    "Daily journal directory path must not contain symlinks"
                )
            current = current.parent
        path = self._root / f"{day.isoformat()}.md"
        if path.parent != self._root or path.name != f"{day.isoformat()}.md":
            raise ValueError("Daily journal path is invalid")
        if path.is_symlink():
            raise DailyJournalStorageError("Daily journal file must not be a symlink")
        return path

    @staticmethod
    def _read_content(path: Path, day: date) -> str:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            raise DailyJournalStorageError("Daily journal note is unavailable") from error
        _parse_note(content, day)
        return content

    def _atomic_write(self, path: Path, content: str) -> None:
        temporary_path: Path | None = None
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._root,
                prefix=".daily-journal-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
            temporary_path = None
            directory_fd = os.open(self._root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            raise DailyJournalStorageError("Daily journal note could not be saved") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _template(day: date) -> str:
    return "\n".join(
        [
            f"# {day.isoformat()}",
            "",
            HEADINGS[0][1],
            "",
            HEADINGS[1][1],
            "",
            HEADINGS[2][1],
            "",
            HEADINGS[3][1],
            "",
            "- [ ]",
            "",
            HEADINGS[4][1],
            "",
        ]
    )


def _parse_note(content: str, day: date) -> dict[DailyJournalSection, list[str]]:
    lines = content.splitlines()
    expected_headings = [heading for _, heading in HEADINGS]
    if not lines or lines[0] != f"# {day.isoformat()}":
        raise DailyJournalStorageError("Daily journal note has an invalid date heading")
    found_headings = [line for line in lines if line.startswith("## ")]
    if found_headings != expected_headings:
        raise DailyJournalStorageError("Daily journal note does not match the required template")
    if any(line.startswith("#") for line in lines[1:] if line not in expected_headings):
        raise DailyJournalStorageError("Daily journal note contains an unexpected heading")
    sections: dict[DailyJournalSection, list[str]] = {}
    heading_to_section = {heading: section for section, heading in HEADINGS}
    current_section: DailyJournalSection | None = None
    for line in lines[1:]:
        section = heading_to_section.get(line)
        if section is not None:
            current_section = section
            sections[section] = []
        elif current_section is not None and line.strip():
            sections[current_section].append(line)
    sections.setdefault(DailyJournalSection.NEXT_STEPS, ["- [ ]"])
    return sections


def _render_note(day: date, sections: dict[DailyJournalSection, list[str]]) -> str:
    lines = [f"# {day.isoformat()}", ""]
    for section, heading in HEADINGS:
        lines.extend((heading, ""))
        body = sections.get(section, [])
        if section == DailyJournalSection.NEXT_STEPS and not body:
            body = ["- [ ]"]
        lines.extend(body)
        lines.append("")
    return "\n".join(lines)


def _apply_changes(content: str, changes: list[DailyJournalChange]) -> str:
    day = date.fromisoformat(content.splitlines()[0][2:])
    sections = _parse_note(content, day)
    for change in changes:
        entries = sections[change.section]
        if change.operation == DailyJournalOperation.ADD:
            entry = (
                f"- [ ] {change.text}"
                if change.section == DailyJournalSection.NEXT_STEPS
                else f"- {change.text}"
            )
            if entry not in entries:
                if change.section == DailyJournalSection.NEXT_STEPS and entries == ["- [ ]"]:
                    entries.clear()
                entries.append(entry)
        elif change.operation == DailyJournalOperation.REPLACE:
            previous_entry = _entry_for(change.section, change.previous_text or "")
            replacement = _entry_for(change.section, change.text)
            if previous_entry not in entries:
                if replacement in entries:
                    continue
                raise DailyJournalConflictError("Entry to replace was not found")
            entries[entries.index(previous_entry)] = replacement
        elif change.operation == DailyJournalOperation.REMOVE:
            previous_entry = _entry_for(change.section, change.previous_text or "")
            if previous_entry not in entries:
                continue
            entries.remove(previous_entry)
        elif change.operation == DailyJournalOperation.COMPLETE_TASK:
            pending = f"- [ ] {change.text}"
            completed = f"- [x] {change.text}"
            if pending not in entries:
                if completed in entries:
                    continue
                raise DailyJournalConflictError("Task to complete was not found")
            entries[entries.index(pending)] = completed
    return _render_note(day, sections)


def _entry_for(section: DailyJournalSection, text: str) -> str:
    if section == DailyJournalSection.NEXT_STEPS:
        return f"- [ ] {text}"
    return f"- {text}"


def _changes_already_applied(content: str, changes: list[DailyJournalChange]) -> bool:
    try:
        updated = _apply_changes(content, changes)
    except DailyJournalConflictError:
        return False
    return updated == content


def _revision(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
