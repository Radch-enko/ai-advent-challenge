from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Query
from pydantic import ValidationError

from copia.expenses.api.cursor import decode_expense_cursor, encode_expense_cursor
from copia.expenses.api.errors import expense_error
from copia.expenses.api.models.expense_page import ExpensePage
from copia.expenses.data.expenses_repository import (
    ExpensesFileNotFoundError,
    ExpensesRepository,
    ExpensesStorageError,
)
from copia.expenses.domain.models.expense_search_filters import ExpenseSearchFilters
from copia.expenses.domain.services.expense_search import filter_expenses


def make_list_expenses(
    get_repository: Callable[[], ExpensesRepository],
) -> Callable[..., ExpensePage]:
    def list_expenses(
        page_size: int = Query(default=20, ge=1, le=100),
        cursor: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        category: str | None = None,
        name: str | None = None,
        merchant: str | None = None,
        payment_method: str | None = None,
        tags: Annotated[list[str] | None, Query()] = None,
        min_amount_rub: Annotated[Decimal | None, Query(ge=0)] = None,
        max_amount_rub: Annotated[Decimal | None, Query(ge=0)] = None,
        text: str | None = None,
    ) -> ExpensePage:
        offset = decode_expense_cursor(cursor)
        try:
            search_filters = ExpenseSearchFilters(
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                category=category,
                name=name,
                merchant=merchant,
                payment_method=payment_method,
                tags=tags or [],
                min_amount_rub=min_amount_rub,
                max_amount_rub=max_amount_rub,
                text=text,
            )
        except ValidationError as error:
            message = error.errors(include_url=False)[0]["msg"]
            raise expense_error("invalid_expense_request", message, 422) from error
        try:
            stored_expenses = filter_expenses(get_repository().list(), search_filters)
        except ExpensesFileNotFoundError as error:
            raise expense_error("finances_file_not_found", str(error), 404) from error
        except ExpensesStorageError as error:
            raise expense_error("finances_storage_error", str(error), 500) from error

        items = stored_expenses[offset : offset + page_size]
        next_offset = offset + len(items)
        next_cursor = (
            encode_expense_cursor(next_offset) if next_offset < len(stored_expenses) else None
        )
        return ExpensePage(items=items, next_cursor=next_cursor)

    return list_expenses
