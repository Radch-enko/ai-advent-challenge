from collections.abc import Awaitable, Callable
from typing import Any

ThreadpoolRunner = Callable[..., Awaitable[Any]]
