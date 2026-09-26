from __future__ import annotations

import re
from datetime import datetime

from copia.providers.domain.models.tool_loop_message import ToolLoopMessage
from copia.sessions.domain.models.chat_message import ChatMessage

_CONTEXT_START = "<current_datetime_context>"
_CONTEXT_END = "</current_datetime_context>"
_CONTEXT_PATTERN = re.compile(
    rf"\n*{re.escape(_CONTEXT_START)}.*?{re.escape(_CONTEXT_END)}",
    re.DOTALL,
)


def render_current_datetime_context(value: datetime | None = None) -> str:
    current = value or datetime.now().astimezone()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Current datetime must include timezone information")
    offset = current.strftime("%z")
    formatted_offset = f"{offset[:3]}:{offset[3:]}"
    return (
        f"{_CONTEXT_START}\n"
        f"Local datetime: {current.isoformat(timespec='seconds')}\n"
        f"Timezone: {current.tzname() or formatted_offset}\n"
        f"UTC offset: {formatted_offset}\n"
        f"{_CONTEXT_END}"
    )


def with_current_datetime_context(
    messages: list[ChatMessage | ToolLoopMessage],
    value: datetime | None = None,
) -> list[ChatMessage | ToolLoopMessage]:
    context = render_current_datetime_context(value)
    updated = list(messages)
    for index, message in enumerate(updated):
        if message.role != "system":
            continue
        base_content = _CONTEXT_PATTERN.sub("", message.content).rstrip()
        content = f"{base_content}\n\n{context}" if base_content else context
        updated[index] = message.model_copy(update={"content": content})
        return updated
    updated.insert(0, ChatMessage(role="system", content=context))
    return updated
