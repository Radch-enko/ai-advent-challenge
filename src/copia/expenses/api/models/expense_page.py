from __future__ import annotations

from pydantic import BaseModel

from copia.expenses.domain.models.expense import Expense


class ExpensePage(BaseModel):
    items: list[Expense]
    next_cursor: str | None = None
