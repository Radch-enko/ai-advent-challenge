from collections.abc import Callable

from fastapi import HTTPException, status


class SessionMessageErrors:
    def __init__(self, get_finish_log: Callable[[], Callable[..., None]]) -> None:
        self._get_finish_log = get_finish_log

    def initialization_error(
        self,
        agent_log_id: str,
        message: str,
        code: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> HTTPException:
        self._get_finish_log()(agent_log_id, status="failed", error=message)
        return HTTPException(
            status_code=status_code,
            detail={"message": message, "code": code, "agent_log_id": agent_log_id},
        )
