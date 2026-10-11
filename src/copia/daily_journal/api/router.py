from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, HTTPException

from copia.daily_journal.api.mappers.daily_journal_mapper import (
    to_domain_change,
    to_note_response,
)
from copia.daily_journal.api.models.daily_journal_note_response import (
    DailyJournalNoteResponse,
)
from copia.daily_journal.api.models.daily_journal_update_request import (
    DailyJournalUpdateRequest,
)
from copia.daily_journal.data.daily_journal_repository import DailyJournalRepository
from copia.daily_journal.domain.errors import (
    DailyJournalConflictError,
    DailyJournalStorageError,
)


def create_daily_journal_router(
    get_repository: Callable[[], DailyJournalRepository],
) -> APIRouter:
    router = APIRouter(prefix="/daily-journal", tags=["daily-journal"])

    @router.get("/{note_date}", response_model=DailyJournalNoteResponse)
    def read_daily_journal(note_date: date) -> DailyJournalNoteResponse:
        try:
            return to_note_response(get_repository().read(note_date))
        except DailyJournalStorageError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @router.patch("/{note_date}", response_model=DailyJournalNoteResponse)
    def update_daily_journal(
        note_date: date, request: DailyJournalUpdateRequest
    ) -> DailyJournalNoteResponse:
        try:
            return get_repository().apply(
                note_date,
                expected_revision=request.expected_revision,
                changes=[to_domain_change(change) for change in request.changes],
            )
        except DailyJournalConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except DailyJournalStorageError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
