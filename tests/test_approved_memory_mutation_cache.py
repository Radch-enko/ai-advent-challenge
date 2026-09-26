from copia.session_memory.application.approved_memory_mutation_cache import (
    ApprovedMemoryMutationCache,
)


def test_cache_evicts_oldest_approval_when_full():
    cache = ApprovedMemoryMutationCache[str](capacity=2)
    cache.put(("session", "first"), "first result")
    cache.put(("session", "second"), "second result")

    cache.put(("session", "third"), "third result")

    assert list(cache.entries) == [("session", "second"), ("session", "third")]


def test_cache_refreshes_existing_approval_order():
    cache = ApprovedMemoryMutationCache[str](capacity=2)
    cache.put(("session", "first"), "original")
    cache.put(("session", "second"), "second result")

    cache.put(("session", "first"), "updated")

    assert list(cache.entries.items()) == [
        (("session", "second"), "second result"),
        (("session", "first"), "updated"),
    ]
