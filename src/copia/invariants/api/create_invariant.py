import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.invariants.domain.models.invariant import Invariant
from copia.invariants.domain.models.invariant_create import InvariantCreate
from copia.sessions.domain.models.chat_session import ChatSession


def make_create_invariant(
    get_repository: Callable[[], InvariantsRepository],
    require_session: Callable[[str], Awaitable[ChatSession]],
) -> tuple[
    Callable[[InvariantCreate], Awaitable[Invariant]],
    Callable[[str, InvariantCreate], Awaitable[Invariant]],
]:
    def save_invariant(request: InvariantCreate) -> Invariant:
        now = datetime.now(UTC)
        invariant = Invariant(
            id=str(uuid.uuid4()), **request.model_dump(), created_at=now, updated_at=now
        )
        try:
            return get_repository().create(invariant)
        except ValueError as error:
            raise HTTPException(status_code=409, detail="Invariant limit reached") from error

    async def create_invariant(request: InvariantCreate) -> Invariant:
        return await run_in_threadpool(save_invariant, request)

    async def create_session_invariant(session_id: str, request: InvariantCreate) -> Invariant:
        await require_session(session_id)
        return await create_invariant(request)

    return create_invariant, create_session_invariant
