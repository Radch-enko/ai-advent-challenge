from copia.daily_journal.api.models.daily_journal_change_request import (
    DailyJournalChangeRequest,
)
from copia.daily_journal.api.models.daily_journal_note_response import (
    DailyJournalNoteResponse,
)
from copia.daily_journal.domain.models.daily_journal_change import DailyJournalChange
from copia.daily_journal.domain.models.daily_journal_note import DailyJournalNote


def to_domain_change(change: DailyJournalChangeRequest) -> DailyJournalChange:
    return DailyJournalChange.model_validate(change.model_dump())


def to_note_response(note: DailyJournalNote) -> DailyJournalNoteResponse:
    return DailyJournalNoteResponse.model_validate(note.model_dump())
