from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AutoClassificationResult(BaseModel):
    should_block: bool
    reason: str
    confidence: Literal["low", "medium", "high"]
    risk_categories: list[str] = Field(default_factory=list)
