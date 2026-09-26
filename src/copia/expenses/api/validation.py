from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def expense_validation_error_response(error: RequestValidationError) -> JSONResponse:
    first_error = error.errors()[0]
    location = ".".join(str(part) for part in first_error["loc"])
    message = f"Invalid {location}: {first_error['msg']}"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": {"code": "invalid_expense_request", "message": message}},
    )
