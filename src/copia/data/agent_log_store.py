from __future__ import annotations

import logging
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock

from ..domain.contracts import AgentLogRepository
from ..domain.models.agent_log import AgentLogExchange, AgentLogOperation, AgentLogTurn
from ..domain.models.config import ProviderName
from ..domain.services.credential_sanitizer import sanitize_error

MAX_AGENT_LOG_BODY_BYTES = 64 * 1024
MAX_AGENT_LOG_TURNS = 100
MAX_AGENT_LOG_EXCHANGES_PER_TURN = 32
MAX_AGENT_LOG_TOTAL_BODY_BYTES = 8 * 1024 * 1024
logger = logging.getLogger(__name__)


@dataclass
class _TurnRecord:
    agent_turn_id: str
    session_id: str
    started_at: datetime
    status: str = "running"
    provider: ProviderName | None = None
    model: str | None = None
    usage: dict[str, int] | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0
    error: str | None = None
    exchanges: list[AgentLogExchange] = field(default_factory=list)
    operations: list[AgentLogOperation] = field(default_factory=list)


class AgentLogStore:
    """Thread-safe bounded cache with optional durable storage for agent turn logs."""

    def __init__(
        self,
        *,
        max_turns: int = MAX_AGENT_LOG_TURNS,
        max_exchanges_per_turn: int = MAX_AGENT_LOG_EXCHANGES_PER_TURN,
        max_body_bytes: int = MAX_AGENT_LOG_BODY_BYTES,
        max_total_body_bytes: int = MAX_AGENT_LOG_TOTAL_BODY_BYTES,
        repository: AgentLogRepository | None = None,
    ) -> None:
        if min(max_turns, max_exchanges_per_turn, max_body_bytes, max_total_body_bytes) < 1:
            raise ValueError("Agent log limits must be positive")
        if max_body_bytes > max_total_body_bytes:
            raise ValueError("The per-body limit cannot exceed the total body limit")
        self.max_turns = max_turns
        self.max_exchanges_per_turn = max_exchanges_per_turn
        self.max_body_bytes = max_body_bytes
        self.max_total_body_bytes = max_total_body_bytes
        self._repository = repository
        self._turns: OrderedDict[str, _TurnRecord] = OrderedDict()
        self._deleted_sessions: set[str] = set()
        self._deleted_session_order: deque[str] = deque()
        self._body_bytes = 0
        self._lock = RLock()

    def start_turn(self, session_id: str, agent_turn_id: str | None = None) -> str:
        turn_id = agent_turn_id or _new_id()
        with self._lock:
            if session_id in self._deleted_sessions:
                return turn_id
            existing = self._turns.get(turn_id)
            if existing is None:
                record = _TurnRecord(
                    agent_turn_id=turn_id,
                    session_id=session_id,
                    started_at=datetime.now(UTC),
                )
                self._turns[turn_id] = record
                self._evict_turns_if_needed()
                self._persist(record)
            elif existing.session_id != session_id:
                raise ValueError("Agent log id belongs to another session")
        return turn_id

    def append(self, exchange: AgentLogExchange) -> bool:
        """Append a sanitized exchange and return whether it was retained."""
        with self._lock:
            if exchange.session_id in self._deleted_sessions:
                return False
            record = self._turns.get(exchange.agent_turn_id)
            if record is None:
                # A hook may arrive after eviction or deletion. Never recreate
                # a turn from a late exchange.
                return False
            if record.session_id != exchange.session_id:
                return False

            bounded = self._bounded_exchange(exchange)
            was_finished = record.completed_at is not None
            if len(record.exchanges) >= self.max_exchanges_per_turn:
                self._body_bytes -= _exchange_body_bytes(record.exchanges.pop(0))
            record.exchanges.append(bounded)
            self._body_bytes += _exchange_body_bytes(bounded)
            self._trim_body_budget()
            record.duration_seconds = max(
                record.duration_seconds, (bounded.created_at - record.started_at).total_seconds()
            )
            if was_finished and record.completed_at is not None:
                record.completed_at = max(record.completed_at, bounded.created_at)
            else:
                record.completed_at = None
            self._turns.move_to_end(exchange.agent_turn_id)
            if self._turns.get(exchange.agent_turn_id) is record:
                self._persist(record)
            return any(item.id == bounded.id for item in record.exchanges)

    def append_operation(self, operation: AgentLogOperation) -> None:
        with self._lock:
            record = self._turns.get(operation.agent_turn_id)
            if record is None or record.session_id != operation.session_id:
                return
            record.operations.append(operation)
            self._persist(record)

    def finish_turn(
        self,
        agent_turn_id: str,
        *,
        provider: ProviderName | None = None,
        model: str | None = None,
        usage: dict[str, int] | None = None,
        status: str = "completed",
        error: str | None = None,
    ) -> None:
        with self._lock:
            record = self._turns.get(agent_turn_id)
            if record is None:
                return
            now = datetime.now(UTC)
            record.provider = provider
            record.model = model
            record.usage = dict(usage) if usage is not None else None
            record.status = status
            record.completed_at = now
            record.duration_seconds = max(0, (now - record.started_at).total_seconds())
            record.error = sanitize_error(error) if error else None
            self._turns.move_to_end(agent_turn_id)
            self._persist(record)

    def get_turn(self, session_id: str, agent_turn_id: str) -> AgentLogTurn | None:
        with self._lock:
            record = self._turns.get(agent_turn_id)
            if record is not None:
                if record.session_id != session_id:
                    return None
                return _snapshot(record)
            if self._repository is None:
                return None
            try:
                return self._repository.load(session_id, agent_turn_id)
            except (OSError, ValueError):
                return None

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            for turn_id, record in list(self._turns.items()):
                if record.session_id == session_id:
                    self._body_bytes -= _record_body_bytes(record)
                    del self._turns[turn_id]
            if session_id not in self._deleted_sessions:
                self._deleted_sessions.add(session_id)
                self._deleted_session_order.append(session_id)
            while len(self._deleted_session_order) > self.max_turns:
                self._deleted_sessions.discard(self._deleted_session_order.popleft())
            if self._repository is not None:
                self._repository.delete_session(session_id)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
            self._deleted_sessions.clear()
            self._deleted_session_order.clear()
            self._body_bytes = 0

    def _bounded_exchange(self, exchange: AgentLogExchange) -> AgentLogExchange:
        request_body, request_truncated = _limit_body(
            exchange.request_body, self.max_body_bytes, exchange.request_body_truncated
        )
        response_body, response_truncated = _limit_body(
            exchange.response_body, self.max_body_bytes, exchange.response_body_truncated
        )
        return exchange.model_copy(
            deep=True,
            update={
                "request_body": request_body,
                "request_body_truncated": request_truncated,
                "response_body": response_body,
                "response_body_truncated": response_truncated,
            },
        )

    def _persist(self, record: _TurnRecord) -> None:
        if self._repository is not None:
            try:
                self._repository.save(_snapshot(record))
            except OSError:
                logger.warning("Could not persist agent log %s", record.agent_turn_id)

    def _delete_persisted(self, record: _TurnRecord) -> None:
        if self._repository is not None:
            try:
                self._repository.delete(record.session_id, record.agent_turn_id)
            except OSError:
                logger.warning("Could not delete persisted agent log %s", record.agent_turn_id)

    def _evict_turns_if_needed(self) -> None:
        while len(self._turns) > self.max_turns:
            _, record = self._turns.popitem(last=False)
            self._body_bytes -= _record_body_bytes(record)
            self._delete_persisted(record)

    def _trim_body_budget(self) -> None:
        while self._body_bytes > self.max_total_body_bytes and self._turns:
            _, record = self._turns.popitem(last=False)
            self._body_bytes -= _record_body_bytes(record)
            self._delete_persisted(record)


def _limit_body(
    body: bytes | None, limit: int, already_truncated: bool
) -> tuple[bytes | None, bool]:
    if body is None or len(body) <= limit:
        return body, already_truncated
    return body[:limit], True


def _exchange_body_bytes(exchange: AgentLogExchange) -> int:
    return len(exchange.request_body or b"") + len(exchange.response_body or b"")


def _record_body_bytes(record: _TurnRecord) -> int:
    return sum(_exchange_body_bytes(exchange) for exchange in record.exchanges)


def _snapshot(record: _TurnRecord) -> AgentLogTurn:
    return AgentLogTurn(
        agent_turn_id=record.agent_turn_id,
        session_id=record.session_id,
        status=record.status,  # type: ignore[arg-type]
        provider=record.provider,
        model=record.model,
        usage=dict(record.usage) if record.usage is not None else None,
        started_at=record.started_at,
        completed_at=record.completed_at,
        duration_seconds=record.duration_seconds,
        error=record.error,
        exchanges=[exchange.model_copy(deep=True) for exchange in record.exchanges],
        operations=[operation.model_copy(deep=True) for operation in record.operations],
    )


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())
