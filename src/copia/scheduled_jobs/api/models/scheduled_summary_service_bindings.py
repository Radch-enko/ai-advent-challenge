from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScheduledSummaryServiceBindings:
    Agent: Callable[[], Any]
    _execute_resolved_tool: Callable[[], Any]
    _resolved_mcp_tools: Callable[[], Any]
    profiles_path: Callable[[], Any]
    router: Callable[[], Any]
