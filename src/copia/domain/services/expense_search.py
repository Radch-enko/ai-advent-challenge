from __future__ import annotations

from ..models.expense import Expense, ExpenseSearchFilters


def filter_expenses(expenses: list[Expense], filters: ExpenseSearchFilters) -> list[Expense]:
    return [expense for expense in expenses if _matches(expense, filters)]


def _matches(expense: Expense, filters: ExpenseSearchFilters) -> bool:
    if filters.occurred_from is not None and expense.occurred_at < filters.occurred_from:
        return False
    if filters.occurred_to is not None and expense.occurred_at > filters.occurred_to:
        return False
    if not _exact(expense.category, filters.category):
        return False
    if not _contains(expense.name, filters.name):
        return False
    if not _contains(expense.merchant, filters.merchant):
        return False
    if not _exact(expense.payment_method, filters.payment_method):
        return False
    if filters.min_amount_rub is not None and expense.amount_rub < filters.min_amount_rub:
        return False
    if filters.max_amount_rub is not None and expense.amount_rub > filters.max_amount_rub:
        return False
    expense_tags = {tag.casefold() for tag in expense.tags}
    if any(tag.casefold() not in expense_tags for tag in filters.tags):
        return False
    if filters.text is not None:
        searchable = (
            expense.name,
            expense.category,
            expense.merchant,
            expense.payment_method,
            expense.note,
            *expense.tags,
        )
        needle = filters.text.casefold()
        if not any(needle in value.casefold() for value in searchable if value is not None):
            return False
    return True


def _exact(value: str | None, expected: str | None) -> bool:
    return expected is None or value is not None and value.casefold() == expected.casefold()


def _contains(value: str | None, expected: str | None) -> bool:
    return expected is None or value is not None and expected.casefold() in value.casefold()
