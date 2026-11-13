"""Typed decisions on a decision model, when the user has set one up.

A decision model (OpenAI or Gemini Decisions) answers typed questions about a
text instead of writing a reply: each field of ``output_type`` is one question,
a ``Literal`` a pick-one and a ``bool`` a yes/no, and every answer comes with a
confidence. It is fast and cheap, but optional, so ``decide`` returns ``None``
when no decision model is configured or the call fails, and the caller keeps
using its language model.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from suzent.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# Decision models answer in a few hundred milliseconds; anything much slower
# is better left to the caller's own fallback.
DECIDE_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class Decided(Generic[T]):
    """A decision model's answers, with how sure it was of each field."""

    output: T
    # Per field, from 0 to 1: the margin of the chosen answer, not the chance it is right.
    confidence: dict[str, float]
    model_id: str

    def confidence_of(self, field_name: str) -> float:
        return self.confidence.get(field_name, 0.0)


def configured_decision_model() -> str | None:
    """The model ID set for the Decision model role, if any."""
    from suzent.core.role_router import ModelRole, get_role_router

    return get_role_router().get_model_id(ModelRole.DECISION_MODEL)


async def decide(
    output_type: type[T],
    state: str,
    *,
    instructions: str,
    model: Any = None,
) -> Decided[T] | None:
    """Answer ``output_type``'s fields about ``state`` on the decision model.

    ``model`` overrides the configured one (tests pass a model object). Returns
    ``None`` when no decision model is set up or the call fails.
    """
    from pydantic_ai import Agent

    model_id = (
        configured_decision_model()
        if model is None
        else getattr(model, "model_name", "decision model")
    )
    if model is None:
        if not model_id:
            return None
        from suzent.core.model_factory import create_decision_model

        try:
            model = create_decision_model(model_id)
        except Exception as exc:
            logger.warning("Decision model {} is unavailable: {}", model_id, exc)
            return None

    agent = Agent(model, output_type=output_type, instructions=instructions)
    try:
        result = await asyncio.wait_for(
            agent.run(state), timeout=DECIDE_TIMEOUT_SECONDS
        )
    except Exception as exc:
        logger.warning("Decision model {} could not decide: {}", model_id, exc)
        return None
    details = result.response.provider_details or {}
    raw_confidence = details.get("confidence") or {}
    confidence = {
        str(key): float(value)
        for key, value in raw_confidence.items()
        if isinstance(value, (int, float))
    }
    return Decided(result.output, confidence, model_id or "")
