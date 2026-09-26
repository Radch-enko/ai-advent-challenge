from copia.session_memory.domain.models.memory_candidate import MemoryCandidate


class DeterministicFakeMemoryClassifier:
    def __init__(self, candidates: list[MemoryCandidate] | None = None) -> None:
        self.candidates = candidates or []

    def classify(self, message, transcript, working_memory, previous_assistant=None):
        return [candidate.model_copy(deep=True) for candidate in self.candidates]
