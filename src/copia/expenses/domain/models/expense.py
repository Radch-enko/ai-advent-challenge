from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import field_validator

from copia.expenses.domain.models.expense_create import ExpenseCreate


class Expense(ExpenseCreate):
    id: UUID
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_created_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone offset")
        return value
