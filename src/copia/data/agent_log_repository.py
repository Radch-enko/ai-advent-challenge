from __future__ import annotations

import base64
import binascii
import json
import os
import shutil
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from ..domain.models.agent_log import AgentLogExchange, AgentLogTurn
from ..domain.models.config import ProviderName
from .path_identifiers import validate_path_identifier

AGENT_LOG_DIRECTORY = "agent_logs"


class JsonAgentLogRepository:
    """Atomically stores each agent turn in a session-scoped JSON file."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()
        self._lock = RLock()

    def save(self, turn: AgentLogTurn) -> None:
        with self._lock:
            _atomic_write(self._path(turn.session_id, turn.agent_turn_id), _turn_payload(turn))

    def load(self, session_id: str, agent_turn_id: str) -> AgentLogTurn | None:
        with self._lock:
            path = self._path(session_id, agent_turn_id)
            if not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _turn_from_payload(payload)

    def delete(self, session_id: str, agent_turn_id: str) -> None:
        with self._lock:
            self._path(session_id, agent_turn_id).unlink(missing_ok=True)

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            logs_path = self._root / validate_path_identifier(session_id, "session ID")
            logs_path /= AGENT_LOG_DIRECTORY
            if logs_path.is_dir():
                shutil.rmtree(logs_path)

    def _path(self, session_id: str, agent_turn_id: str) -> Path:
        validate_path_identifier(session_id, "session ID")
        validate_path_identifier(agent_turn_id, "agent log ID")
        return self._root / session_id / AGENT_LOG_DIRECTORY / f"{agent_turn_id}.json"


def _turn_payload(turn: AgentLogTurn) -> dict[str, object]:
    return {
        "agent_turn_id": turn.agent_turn_id,
        "session_id": turn.session_id,
        "status": turn.status,
        "provider": _provider_value(turn.provider),
        "model": turn.model,
        "usage": turn.usage,
        "started_at": turn.started_at.isoformat(),
        "completed_at": turn.completed_at.isoformat() if turn.completed_at else None,
        "duration_seconds": turn.duration_seconds,
        "error": turn.error,
        "exchanges": [_exchange_payload(exchange) for exchange in turn.exchanges],
    }


def _exchange_payload(exchange: AgentLogExchange) -> dict[str, object]:
    return {
        "id": exchange.id,
        "agent_turn_id": exchange.agent_turn_id,
        "session_id": exchange.session_id,
        "operation": exchange.operation,
        "provider": _provider_value(exchange.provider),
        "model": exchange.model,
        "method": exchange.method,
        "url": exchange.url,
        "request_headers": exchange.request_headers,
        "request_body": _body_payload(exchange.request_body),
        "request_body_truncated": exchange.request_body_truncated,
        "status_code": exchange.status_code,
        "response_headers": exchange.response_headers,
        "response_body": _body_payload(exchange.response_body),
        "response_body_truncated": exchange.response_body_truncated,
        "duration_seconds": exchange.duration_seconds,
        "error": exchange.error,
        "created_at": exchange.created_at.isoformat(),
    }


def _body_payload(body: bytes | None) -> dict[str, str] | None:
    if body is None:
        return None
    try:
        return {"encoding": "utf-8", "content": body.decode("utf-8")}
    except UnicodeDecodeError:
        return {
            "encoding": "base64",
            "content": base64.b64encode(body).decode("ascii"),
        }


def _turn_from_payload(payload: Any) -> AgentLogTurn:
    if not isinstance(payload, dict) or not isinstance(payload.get("exchanges"), list):
        raise ValueError("Invalid agent log file")
    data = dict(payload)
    exchanges: list[dict[str, object]] = []
    for item in payload["exchanges"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid agent log exchange")
        exchange = dict(item)
        exchange["request_body"] = _body_from_payload(exchange.get("request_body"))
        exchange["response_body"] = _body_from_payload(exchange.get("response_body"))
        exchanges.append(exchange)
    data["exchanges"] = exchanges
    return AgentLogTurn.model_validate(data)


def _body_from_payload(payload: Any) -> bytes | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("Invalid agent log body")
    encoding = payload.get("encoding")
    content = payload.get("content")
    if not isinstance(encoding, str) or not isinstance(content, str):
        raise ValueError("Invalid agent log body")
    if encoding == "utf-8":
        return content.encode("utf-8")
    if encoding == "base64":
        try:
            return base64.b64decode(content.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error, ValueError) as error:
            raise ValueError("Invalid base64 agent log body") from error
    raise ValueError("Invalid agent log body encoding")


def _provider_value(provider: ProviderName | None) -> str | None:
    return provider.value if provider is not None else None


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".agent-log-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
