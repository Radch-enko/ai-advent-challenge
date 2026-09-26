from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class McpApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
