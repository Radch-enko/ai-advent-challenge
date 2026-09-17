from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from ..models.agent_log import AgentLogContext
from ..models.config import ProviderName

_current_context: ContextVar[AgentLogContext | None] = ContextVar(
    "copia_agent_log_context", default=None
)


def current_agent_log_context() -> AgentLogContext | None:
    context = _current_context.get()
    return context.model_copy(deep=True) if context is not None else None


@contextmanager
def install_agent_log_context(context: AgentLogContext) -> Iterator[None]:
    token = _current_context.set(context)
    try:
        yield
    finally:
        _current_context.reset(token)


@contextmanager
def agent_log_turn(
    session_id: str,
    agent_turn_id: str,
    *,
    provider: ProviderName | None = None,
    model: str | None = None,
    operation: str = "primary",
) -> Iterator[None]:
    with install_agent_log_context(
        AgentLogContext(
            agent_turn_id=agent_turn_id,
            session_id=session_id,
            operation=operation,
            provider=provider,
            model=model,
        )
    ):
        yield


@contextmanager
def agent_log_operation(
    operation: str,
    *,
    provider: ProviderName | None = None,
    model: str | None = None,
) -> Iterator[None]:
    current = _current_context.get()
    if current is None:
        yield
        return

    with install_agent_log_context(
        current.model_copy(
            update={
                "operation": operation,
                "provider": provider if provider is not None else current.provider,
                "model": model if model is not None else current.model,
            }
        )
    ):
        yield
