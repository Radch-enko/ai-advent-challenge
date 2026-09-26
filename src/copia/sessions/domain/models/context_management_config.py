from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from copia.sessions.domain.models.context_strategy_name import ContextStrategyName
from copia.sessions.domain.models.facts_updater_config import FactsUpdaterConfig
from copia.sessions.domain.models.summarizer_config import SummarizerConfig


class ContextManagementConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    strategy: ContextStrategyName = ContextStrategyName.SUMMARY
    recent_message_limit: int = Field(
        default=10,
        ge=1,
        description="Number of recent transcript messages sent by Sliding Window",
    )
    recent_exchange_limit: int = Field(
        default=10,
        ge=1,
        description="Number of recent user-assistant pairs kept verbatim",
    )
    summary_batch_exchange_count: int = Field(
        default=10,
        ge=1,
        description="Number of complete user-assistant pairs summarized per batch",
    )
    summarizer: SummarizerConfig = Field(default_factory=SummarizerConfig)
    facts_updater: FactsUpdaterConfig = Field(default_factory=FactsUpdaterConfig)
