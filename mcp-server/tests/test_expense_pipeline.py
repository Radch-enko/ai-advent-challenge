from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal

import server as finances_server


def run(coroutine):
    return asyncio.run(coroutine)


def expense(name: str, category: str, amount: str) -> finances_server.Expense:
    return finances_server.Expense(
        id="00000000-0000-0000-0000-000000000001",
        occurred_at=datetime.fromisoformat("2026-09-23T14:30:00+06:00"),
        name=name,
        category=category,
        amount_rub=Decimal(amount),
        created_at=datetime.fromisoformat("2026-09-23T08:30:00+00:00"),
    )


def test_compare_expense_periods_uses_decimal_and_union_of_categories() -> None:
    result = finances_server.compare_expense_periods(
        finances_server.ExpenseComparisonRequest(
            current_expenses=[expense("Lunch", "Food", "700.10")],
            previous_expenses=[expense("Coffee", "Food", "200.20"), expense("Taxi", "Travel", "99.80")],
        )
    )

    assert result.current_total_rub == Decimal("700.10")
    assert result.previous_total_rub == Decimal("300.00")
    assert result.difference_rub == Decimal("400.10")
    assert result.percentage_change == Decimal("133.3666666666666666666666667")
    assert [(item.category, item.difference_rub) for item in result.categories] == [
        ("Food", Decimal("499.90")),
        ("Travel", Decimal("-99.80")),
    ]
    assert [point.label for point in result.chart_data] == ["Food", "Travel"]


def test_compare_expense_periods_returns_none_percentage_for_empty_previous_period() -> None:
    result = finances_server.compare_expense_periods(
        finances_server.ExpenseComparisonRequest(
            current_expenses=[expense("Lunch", "Food", "700.10")],
        )
    )

    assert result.previous_total_rub == Decimal("0")
    assert result.percentage_change is None


def test_save_expense_chart_returns_png_content_and_metadata() -> None:
    comparison = finances_server.compare_expense_periods(
        finances_server.ExpenseComparisonRequest(
            current_expenses=[expense("Lunch", "Food", "700.10")],
            previous_expenses=[expense("Coffee", "Food", "200.20")],
        )
    )

    result = run(finances_server.save_expense_chart(comparison))

    image = next(item for item in result.content if item.type == "image")
    assert image.mime_type == "image/png"
    assert image.data.startswith("iVBORw0KGgo")
    assert result.structured_content == {
        "filename": "expense-comparison.png",
        "mime_type": "image/png",
        "title": "Expense comparison",
    }
