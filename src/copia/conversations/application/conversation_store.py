from __future__ import annotations

import hashlib
import json
import threading
import uuid
from pathlib import Path
from typing import Any

from copia.conversations.application.conversation_run import (
    ConversationEventLimitExceeded,
    ConversationRun,
)
from copia.conversations.data.conversation_repository import (
    ConversationRepository,
    ConversationStorageLimitError,
)


class ConversationConflictError(ValueError):
    pass


class ConversationStore:
    def __init__(self, path: Path | str = ":memory:") -> None:
        self._lock = threading.RLock()
        self._repository = ConversationRepository(path)
        self._runs: dict[str, ConversationRun] = {}
        self._request_ids: dict[str, str] = {}
        for record in self._repository.load():
            run = ConversationRun(
                id=record["id"],
                request_id=record["request_id"],
                fingerprint=record["fingerprint"],
                status=record["status"],
                events=record["events"],
                persist_event=self._persist_event,
            )
            self._runs[run.id] = run
            self._request_ids[run.request_id] = run.id
            if run.status == "running":
                run.emit(
                    "conversation.failed",
                    {
                        "conversation_id": run.id,
                        "code": "interrupted_by_restart",
                        "message": "Conversation was interrupted when the backend restarted",
                    },
                )

    def create(self, request_id: str, request: dict[str, object]) -> tuple[ConversationRun, bool]:
        fingerprint = _fingerprint(request)
        with self._lock:
            existing = self._find_request(request_id)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise ConversationConflictError("request_id was already used")
                return existing, False
            run = ConversationRun(
                str(uuid.uuid4()),
                request_id,
                fingerprint,
                persist_event=self._persist_event,
            )
            try:
                created = self._repository.create(run.id, request_id, fingerprint)
            except ConversationStorageLimitError as error:
                raise ConversationStorageLimitError("Conversation storage is full") from error
            if not created:
                existing = self._find_request(request_id)
                if existing is None:
                    raise ConversationStorageLimitError("Conversation storage is full")
                if existing.fingerprint != fingerprint:
                    raise ConversationConflictError("request_id was already used")
                return existing, False
            self._runs[run.id] = run
            self._request_ids[request_id] = run.id
            self._prune_memory_cache()
            try:
                run.emit(
                    "conversation.started",
                    {"conversation_id": run.id, "request_id": request_id},
                )
            except ConversationEventLimitExceeded:
                pass
            return run, True

    def find_request(self, request_id: str, request: dict[str, object]) -> ConversationRun | None:
        fingerprint = _fingerprint(request)
        with self._lock:
            run = self._find_request(request_id)
            if run is None:
                return None
            if run.fingerprint != fingerprint:
                raise ConversationConflictError("request_id was already used")
            return run

    def _find_request(self, request_id: str) -> ConversationRun | None:
        conversation_id = self._request_ids.get(request_id)
        if conversation_id is None:
            conversation_id = self._repository.get_by_request_id(request_id)
            if conversation_id is None:
                return None
            run = self._runs.get(conversation_id)
            if run is None:
                return None
            self._request_ids[request_id] = conversation_id
            return run
        if self._repository.get_by_id(conversation_id) is None:
            self._request_ids.pop(request_id, None)
            self._runs.pop(conversation_id, None)
            return None
        return self._runs.get(conversation_id)

    def _persist_event(self, conversation_id: str, sequence: int, event: dict[str, Any]) -> bool:
        return self._repository.append_event(conversation_id, sequence, event)

    def _prune_memory_cache(self) -> None:
        retained_ids = self._repository.conversation_ids()
        with self._lock:
            for conversation_id, run in tuple(self._runs.items()):
                if conversation_id not in retained_ids:
                    self._runs.pop(conversation_id, None)
                    self._request_ids.pop(run.request_id, None)

    def get(self, conversation_id: str) -> ConversationRun | None:
        with self._lock:
            run = self._runs.get(conversation_id)
            if run is not None and self._repository.get_by_id(conversation_id) is not None:
                result = run
            else:
                self._runs.pop(conversation_id, None)
                result = None
        self._prune_memory_cache()
        return result

    def get_by_request_id(self, request_id: str) -> ConversationRun | None:
        with self._lock:
            result = self._find_request(request_id)
        self._prune_memory_cache()
        return result

    def find_pending_approval(self, session_id: str, approval_id: str) -> ConversationRun | None:
        with self._lock:
            return next(
                (
                    run
                    for run in self._runs.values()
                    if run.session_id == session_id
                    and run.approval is not None
                    and run.approval.id == approval_id
                ),
                None,
            )

    def has_active_session(self, session_id: str) -> bool:
        with self._lock:
            return any(
                run.session_id == session_id and run.status in {"running", "waiting_for_approval"}
                for run in self._runs.values()
            )

    def claim_session(self, conversation_id: str, session_id: str) -> bool:
        with self._lock:
            if any(
                run.id != conversation_id
                and run.session_claimed
                and run.session_id == session_id
                and run.status in {"running", "waiting_for_approval"}
                for run in self._runs.values()
            ):
                return False
            run = self._runs.get(conversation_id)
            if run is None:
                return False
            run.session_id = session_id
            run.session_claimed = True
            return True

    def release_session(self, conversation_id: str) -> None:
        with self._lock:
            run = self._runs.get(conversation_id)
            if run is not None:
                run.session_claimed = False

    def close(self) -> None:
        self._repository.close()

    @staticmethod
    def event_index(run: ConversationRun, event_id: str | None) -> int:
        if event_id is None:
            return 0
        for index, event in enumerate(run.events, start=1):
            if event["id"] == event_id:
                return index
        raise ValueError("Event ID is outside the retained event range")


def _fingerprint(request: dict[str, object]) -> str:
    encoded = json.dumps(request, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
