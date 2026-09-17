from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..contracts import WorkingMemoryStore
from ..models.memory import MemoryCandidate, MemoryEvent, PendingMemorySuggestion, WorkingMemoryItem


class HybridMemoryPolicy:
    def apply(
        self,
        session_id: str,
        candidates: list[MemoryCandidate],
        store: WorkingMemoryStore,
        pending: list[PendingMemorySuggestion] | None = None,
    ) -> tuple[list[WorkingMemoryItem], list[PendingMemorySuggestion], list[MemoryEvent]]:
        items = store.load(session_id)
        original = [item.model_copy(deep=True) for item in items]
        pending_result: list[PendingMemorySuggestion] = []
        pending_keys: set[str] = set()
        for suggestion in pending or []:
            key = suggestion.candidate.model_dump_json()
            if key not in pending_keys:
                pending_keys.add(key)
                pending_result.append(suggestion)
        events: list[MemoryEvent] = []
        for candidate in candidates:
            if candidate.scope == "none" or candidate.action == "skip":
                continue
            if candidate.confidence < 0.6:
                events.append(
                    MemoryEvent(
                        id=str(uuid.uuid4()),
                        scope="working",
                        action="error",
                        key=candidate.key,
                        message="Memory candidate requires clarification",
                    )
                )
                continue
            if candidate.scope == "long_term":
                suggestion = PendingMemorySuggestion(
                    id=str(uuid.uuid4()), candidate=candidate, created_at=datetime.now(UTC)
                )
                candidate_key = candidate.model_dump_json()
                if candidate_key not in pending_keys:
                    pending_keys.add(candidate_key)
                    pending_result.append(suggestion)
                    events.append(
                        MemoryEvent(
                            id=str(uuid.uuid4()),
                            scope="long_term",
                            action="proposed",
                            key=candidate.key,
                            candidate_id=suggestion.id,
                        )
                    )
                continue
            existing = next((item for item in items if item.key == candidate.key), None)
            if candidate.action == "delete":
                if existing:
                    items.remove(existing)
                    events.append(
                        MemoryEvent(
                            id=str(uuid.uuid4()),
                            scope="working",
                            action="deleted",
                            key=candidate.key,
                        )
                    )
            elif candidate.value is not None:
                now = datetime.now(UTC)
                if existing:
                    existing.value = candidate.value
                    existing.updated_at = now
                    events.append(
                        MemoryEvent(
                            id=str(uuid.uuid4()),
                            scope="working",
                            action="updated",
                            key=candidate.key,
                            value=candidate.value,
                        )
                    )
                else:
                    item = WorkingMemoryItem(
                        id=str(uuid.uuid4()),
                        key=candidate.key,
                        value=candidate.value,
                        created_at=now,
                        updated_at=now,
                    )
                    items.append(item)
                    events.append(
                        MemoryEvent(
                            id=str(uuid.uuid4()),
                            scope="working",
                            action="created",
                            key=item.key,
                            value=item.value,
                        )
                    )
        if items != original:
            save_automatic = getattr(store, "save_automatic", None)
            if save_automatic is not None:
                save_automatic(session_id, original, items)
            else:
                store.save(session_id, items)
        return items, pending_result, events
