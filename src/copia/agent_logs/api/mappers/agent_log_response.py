from __future__ import annotations

import base64
from typing import Literal

from copia.agent_logs.api.models.agent_log_body_response import AgentLogBodyResponse
from copia.agent_logs.api.models.agent_log_exchange_response import AgentLogExchangeResponse
from copia.agent_logs.api.models.agent_log_response import AgentLogResponse
from copia.agent_logs.domain.models.agent_log_exchange import AgentLogExchange
from copia.agent_logs.domain.models.agent_log_turn import AgentLogTurn


def agent_log_response(turn: AgentLogTurn) -> AgentLogResponse:
    return AgentLogResponse(
        agent_log_id=turn.agent_turn_id,
        agent_turn_id=turn.agent_turn_id,
        session_id=turn.session_id,
        status=turn.status,
        provider=turn.provider,
        model=turn.model,
        usage=turn.usage,
        started_at=turn.started_at,
        completed_at=turn.completed_at,
        duration_seconds=turn.duration_seconds,
        error=turn.error,
        operations=turn.operations,
        exchanges=[agent_log_exchange_response(exchange) for exchange in turn.exchanges],
        tool_calls=turn.tool_calls,
    )


def agent_log_exchange_response(exchange: AgentLogExchange) -> AgentLogExchangeResponse:
    return AgentLogExchangeResponse(
        id=exchange.id,
        agent_turn_id=exchange.agent_turn_id,
        operation=exchange.operation,
        provider=exchange.provider,
        model=exchange.model,
        method=exchange.method,
        url=exchange.url,
        request_headers=exchange.request_headers,
        request_body=agent_log_body(exchange.request_body, exchange.request_body_truncated),
        status_code=exchange.status_code,
        response_headers=exchange.response_headers,
        response_body=agent_log_body(exchange.response_body, exchange.response_body_truncated),
        duration_seconds=exchange.duration_seconds,
        error=exchange.error,
        created_at=exchange.created_at,
    )


def agent_log_body(body: bytes | None, truncated: bool) -> AgentLogBodyResponse | None:
    if body is None:
        return None
    try:
        content = body.decode("utf-8")
        encoding: Literal["utf-8", "base64"] = "utf-8"
    except UnicodeDecodeError:
        content = base64.b64encode(body).decode("ascii")
        encoding = "base64"
    return AgentLogBodyResponse(
        content=content,
        encoding=encoding,
        size_bytes=len(body),
        truncated=truncated,
    )
