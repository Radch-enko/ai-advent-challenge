from collections.abc import Callable

from copia.expenses.api.errors import expense_error
from copia.expenses.data.expenses_repository import (
    ExpensesFileNotFoundError,
    ExpensesRepository,
    ExpensesStorageError,
)
from copia.expenses.domain.models.expense import Expense
from copia.expenses.domain.models.expense_create import ExpenseCreate


def make_create_expense(
    get_repository: Callable[[], ExpensesRepository],
) -> Callable[[ExpenseCreate], Expense]:
    def create_expense(request: ExpenseCreate) -> Expense:
        try:
            return get_repository().add(request)
        except ExpensesFileNotFoundError as error:
            raise expense_error("finances_file_not_found", str(error), 404) from error
        except ExpensesStorageError as error:
            raise expense_error("finances_storage_error", str(error), 500) from error

    return create_expense
