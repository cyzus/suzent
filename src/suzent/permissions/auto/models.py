from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AutoClassificationResult(BaseModel):
    should_block: bool
    reason: str = Field(
        description=(
            "Shown to the user: one or two sentences in the language of the "
            "user's latest request, with tool names and arguments verbatim."
        )
    )
    confidence: Literal["low", "medium", "high"]
    risk_categories: list[str] = Field(default_factory=list)
    reviewer_model: str | None = None
