import base64
import binascii

from copia.expenses.api.errors import expense_error


def encode_expense_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii").rstrip("=")


def decode_expense_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(cursor + padding, altchars=b"-_", validate=True).decode("ascii")
        offset = int(decoded)
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise expense_error("invalid_cursor", "Expense cursor is invalid", 422) from error
    if offset < 0:
        raise expense_error("invalid_cursor", "Expense cursor is invalid", 422)
    return offset
