from collections.abc import Callable

from fastapi import APIRouter, status

from copia.expenses.api.create_expense import make_create_expense
from copia.expenses.api.list_expenses import make_list_expenses
from copia.expenses.api.models.expense_page import ExpensePage
from copia.expenses.data.expenses_repository import ExpensesRepository
from copia.expenses.domain.models.expense import Expense


def create_expenses_router(get_repository: Callable[[], ExpensesRepository]) -> APIRouter:
    router = APIRouter()
    router.add_api_route(
        "/expenses",
        make_list_expenses(get_repository),
        methods=["GET"],
        response_model=ExpensePage,
    )
    router.add_api_route(
        "/expenses",
        make_create_expense(get_repository),
        methods=["POST"],
        response_model=Expense,
        status_code=status.HTTP_201_CREATED,
    )
    return router
