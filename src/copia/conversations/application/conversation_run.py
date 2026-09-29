from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from copia.mcp.domain.models.mcp_approval import McpApproval


class ConversationEventLimitExceeded(RuntimeError):
    pass


@dataclass
class ConversationRun:
    id: str
    request_id: str
    fingerprint: str
    status: str = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=threading.Condition)
    persist_event: Callable[[str, int, dict[str, Any]], bool] | None = None
    session_id: str | None = None
    session_claimed: bool = False
    approval: McpApproval | None = None
    decision: bool | None = None
    decision_event: threading.Event = field(default_factory=threading.Event)

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        with self.condition:
            sequence = len(self.events) + 1
            event = {"id": f"{self.id}:{sequence}", "event": event_type, "data": data}
            if self.persist_event is not None and not self.persist_event(self.id, sequence, event):
                if event_type not in {"conversation.completed", "conversation.failed"}:
                    event = {
                        "id": f"{self.id}:{sequence}",
                        "event": "conversation.failed",
                        "data": {
                            "conversation_id": self.id,
                            "code": "conversation_storage_limit",
                            "message": "Conversation event storage limit was reached",
                        },
                    }
                    event_type = "conversation.failed"
                    data = event["data"]
                    self.persist_event(self.id, sequence, event)
                    self.events.append(event)
                    self.status = "failed"
                    self.condition.notify_all()
                    raise ConversationEventLimitExceeded("Conversation storage limit exceeded")
            self.events.append(event)
            if event_type in {"conversation.completed", "conversation.failed"}:
                self.status = "completed" if event_type == "conversation.completed" else "failed"
            self.condition.notify_all()

    def wait_for_events(self, index: int, timeout: float) -> list[dict[str, Any]]:
        with self.condition:
            if index >= len(self.events) and self.status not in {"completed", "failed"}:
                self.condition.wait(timeout)
            return list(self.events[index:])

    def request_approval(self, approval: McpApproval) -> bool:
        with self.condition:
            if self.approval is None or self.approval.id != approval.id:
                self.approval = approval
                self.status = "waiting_for_approval"
                self.decision = None
                self.decision_event.clear()
            self.condition.notify_all()
        self.decision_event.wait()
        with self.condition:
            decision = bool(self.decision)
            self.approval = None
            self.status = "running"
            self.condition.notify_all()
            return decision

    def prepare_approval(self, approval: McpApproval) -> None:
        with self.condition:
            self.approval = approval
            self.status = "waiting_for_approval"
            self.decision = None
            self.decision_event.clear()
            self.condition.notify_all()

    def decide_approval(self, approval_id: str, decision: bool) -> bool:
        with self.condition:
            if self.approval is None or self.approval.id != approval_id:
                return False
            if self.decision is not None:
                raise ValueError("Approval was already decided")
            self.decision = decision
            self.decision_event.set()
            return True
