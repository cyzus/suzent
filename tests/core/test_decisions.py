from typing import Literal

import pytest
from pydantic import BaseModel, Field

from suzent.core import decisions


class Verdict(BaseModel):
    """Whether a message needs the user."""

    handling: Literal["reply", "ignore"] = Field(description="What should happen?")
    urgent: bool = Field(description="Is it urgent?")


@pytest.mark.asyncio
async def test_decide_returns_typed_answers_with_confidence(fake_decision_model):
    model = fake_decision_model(lambda _key, options: options[-1], confidence=0.7)

    decided = await decisions.decide(
        Verdict, "The build is on fire", instructions="Triage.", model=model
    )

    assert decided.output == Verdict(handling="ignore", urgent=True)
    assert decided.confidence_of("handling") == pytest.approx(0.7)
    assert decided.model_id == "fake-decider"
    [request] = model.requests
    assert request.state == "The build is on fire"
    assert set(request.questions) == {"handling", "urgent"}


@pytest.mark.asyncio
async def test_decide_is_none_without_a_configured_model(monkeypatch):
    monkeypatch.setattr(decisions, "configured_decision_model", lambda: None)

    assert await decisions.decide(Verdict, "x", instructions="Triage.") is None


@pytest.mark.asyncio
async def test_decide_is_none_when_the_model_fails(fake_decision_model):
    model = fake_decision_model(fail=True)

    assert (
        await decisions.decide(Verdict, "x", instructions="Triage.", model=model)
        is None
    )
