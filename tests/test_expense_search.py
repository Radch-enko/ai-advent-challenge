from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from copia import service
from copia.expenses.domain.models.expense import Expense
from copia.expenses.domain.models.expense_search_filters import ExpenseSearchFilters
from copia.expenses.domain.services.expense_search import filter_expenses
from copia.service import app


def _expense(
    suffix: int,
    occurred_at: str,
    *,
    name: str = "Weekly groceries",
    category: str = "Food",
    amount: str = "100.00",
    merchant: str | None = "Market",
    payment_method: str | None = "Card",
    note: str | None = "Family purchase",
    tags: list[str] | None = None,
) -> Expense:
    return Expense(
        id=UUID(f"00000000-0000-0000-0000-{suffix:012d}"),
        occurred_at=datetime.fromisoformat(occurred_at),
        name=name,
        category=category,
        amount_rub=Decimal(amount),
        merchant=merchant,
        payment_method=payment_method,
        note=note,
        tags=tags or ["weekly", "family"],
        created_at=datetime.fromisoformat("2026-09-23T08:00:00+00:00"),
    )


EXPENSES = [
    _expense(1, "2026-09-20T10:00:00+06:00"),
    _expense(
        2,
        "2026-09-21T10:00:00+06:00",
        name="Gym membership",
        category="Sport",
        amount="2500.00",
        merchant="Fitness Club",
        payment_method="Cash",
        note="Annual plan",
        tags=["health", "annual"],
    ),
    _expense(3, "2026-09-22T10:00:00+06:00", amount="500.00"),
]


@pytest.mark.parametrize(
    ("filters", "expected_ids"),
    [
        (ExpenseSearchFilters(category="fOoD"), [1, 3]),
        (ExpenseSearchFilters(name="member"), [2]),
        (ExpenseSearchFilters(merchant="fitness"), [2]),
        (ExpenseSearchFilters(payment_method="cAsH"), [2]),
        (ExpenseSearchFilters(tags=["HEALTH", "annual"]), [2]),
        (ExpenseSearchFilters(min_amount_rub=Decimal("500")), [2, 3]),
        (ExpenseSearchFilters(max_amount_rub=Decimal("100")), [1]),
        (ExpenseSearchFilters(text="family"), [1, 3]),
        (ExpenseSearchFilters(text="sport"), [2]),
        (
            ExpenseSearchFilters(
                occurred_from=datetime.fromisoformat("2026-09-21T10:00:00+06:00"),
                occurred_to=datetime.fromisoformat("2026-09-22T10:00:00+06:00"),
            ),
            [2, 3],
        ),
    ],
)
def test_filter_expenses_supports_search_contract(filters, expected_ids) -> None:
    result = filter_expenses(EXPENSES, filters)

    assert [int(str(expense.id)[-12:]) for expense in result] == expected_ids


def test_filter_expenses_combines_filters() -> None:
    result = filter_expenses(
        EXPENSES,
        ExpenseSearchFilters(
            category="food",
            tags=["weekly", "family"],
            min_amount_rub=Decimal("200"),
            text="market",
        ),
    )

    assert [expense.amount_rub for expense in result] == [Decimal("500.00")]


def test_expenses_api_filters_before_cursor_pagination(monkeypatch) -> None:
    class Repository:
        def list(self):
            return list(reversed(EXPENSES))

    monkeypatch.setattr(service, "expenses", Repository())
    client = TestClient(app)

    first = client.get("/expenses", params={"category": "food", "page_size": 1})
    second = client.get(
        "/expenses",
        params={
            "category": "food",
            "page_size": 1,
            "cursor": first.json()["next_cursor"],
        },
    )

    assert first.status_code == 200
    assert first.json()["items"][0]["amount_rub"] == "500.00"
    assert second.status_code == 200
    assert second.json()["items"][0]["amount_rub"] == "100.00"
    assert second.json()["next_cursor"] is None


@pytest.mark.parametrize(
    "params",
    [
        {
            "occurred_from": "2026-09-22T10:00:00+06:00",
            "occurred_to": "2026-09-21T10:00:00+06:00",
        },
        {"min_amount_rub": "100", "max_amount_rub": "10"},
        {"occurred_from": "2026-09-22T10:00:00"},
    ],
)
def test_expenses_api_rejects_invalid_search_ranges(monkeypatch, params) -> None:
    class Repository:
        def list(self):
            return EXPENSES

    monkeypatch.setattr(service, "expenses", Repository())

    response = TestClient(app).get("/expenses", params=params)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_expense_request"
