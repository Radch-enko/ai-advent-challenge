from collections import OrderedDict
from typing import Generic, TypeVar

Response = TypeVar("Response")


class ApprovedMemoryMutationCache(Generic[Response]):
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.entries: OrderedDict[tuple[str, str], Response] = OrderedDict()

    def put(self, key: tuple[str, str], response: Response) -> None:
        self.entries[key] = response
        self.entries.move_to_end(key)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
