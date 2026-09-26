from __future__ import annotations

from enum import StrEnum


class ContextStrategyName(StrEnum):
    SUMMARY = "summary"
    SLIDING_WINDOW = "sliding_window"
    STICKY_FACTS = "sticky_facts"
    BRANCHING = "branching"
