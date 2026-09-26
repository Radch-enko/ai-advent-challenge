from datetime import UTC, datetime

from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.models.memory_candidate import MemoryCandidate
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.session_memory.domain.services.deterministic_fake_memory_classifier import (
    DeterministicFakeMemoryClassifier,
)
from copia.session_memory.domain.services.hybrid_memory_policy import HybridMemoryPolicy


def test_working_memory_repository_is_atomic_round_trip_and_session_scoped(tmp_path):
    repository = WorkingMemoryRepository(tmp_path)
    item = WorkingMemoryItem(
        id="one",
        key="deadline",
        value="Friday",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.save("session-a", [item])
    assert repository.load("session-a")[0].value == "Friday"
    assert repository.load("session-b") == []
    assert (tmp_path / "session-a" / "working_memory.json").is_file()


def test_hybrid_policy_applies_working_and_holds_long_term_until_approval(tmp_path):
    repository = WorkingMemoryRepository(tmp_path)
    candidates = [
        MemoryCandidate(
            scope="working",
            action="create",
            key="goal",
            value="Ship",
            confidence=0.9,
            reason="explicit",
        ),
        MemoryCandidate(
            scope="long_term",
            action="create",
            category="profile",
            key="language",
            value="Russian",
            confidence=0.9,
            reason="explicit",
        ),
    ]
    items, pending, events = HybridMemoryPolicy().apply("session", candidates, repository)
    assert items[0].value == "Ship"
    assert pending[0].candidate.value == "Russian"
    assert repository.load("session") == items
    assert {(event.scope, event.action) for event in events} == {
        ("working", "created"),
        ("long_term", "proposed"),
    }


def test_deterministic_classifier_returns_structured_candidates_without_llm():
    candidate = MemoryCandidate(
        scope="working", action="update", key="goal", value="Next", confidence=1, reason="test"
    )
    result = DeterministicFakeMemoryClassifier([candidate]).classify("message", [], [])
    assert result == [candidate]
