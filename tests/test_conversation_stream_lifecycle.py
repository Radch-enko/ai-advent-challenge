from __future__ import annotations

import asyncio

from copia.conversations.api.router import _stream_response


class _WaitingRun:
    status = "waiting_for_approval"

    def wait_for_events(self, index: int, timeout: float) -> list[dict[str, object]]:
        return []


class _ConnectedRequest:
    def __init__(self) -> None:
        self.disconnect_checks = 0

    async def is_disconnected(self) -> bool:
        self.disconnect_checks += 1
        return self.disconnect_checks > 1


def test_sse_stream_stays_open_while_approval_is_pending(monkeypatch) -> None:
    async def no_events_in_thread(*args, **kwargs):
        return []

    monkeypatch.setattr("copia.conversations.api.router.asyncio.to_thread", no_events_in_thread)
    request = _ConnectedRequest()
    response = _stream_response(_WaitingRun(), 0, request)  # type: ignore[arg-type]

    async def collect_chunks() -> list[str]:
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(collect_chunks())

    assert chunks == [": keep-alive\n\n"]
