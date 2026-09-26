from fastapi import HTTPException, status


def memory_storage_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Long-term memory storage is unavailable",
    )
