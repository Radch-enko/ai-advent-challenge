from fastapi import HTTPException, status


class SessionMessageErrors:
    def initialization_error(
        self,
        message: str,
        code: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> HTTPException:
        return HTTPException(
            status_code=status_code,
            detail={"message": message, "code": code},
        )
