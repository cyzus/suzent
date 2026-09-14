"""Keep native-client fixtures compatible with the backend's Node models."""

import json
from pathlib import Path

import pytest

from suzent.nodes.models import (
    ConnectedResponse,
    ConnectMessage,
    InvokeMessage,
    PendingResponse,
    ResultMessage,
)

FIXTURES = (
    Path(__file__).resolve().parents[2] / "packages/mobile-contract/fixtures.json"
)


@pytest.mark.parametrize(
    ("key", "model"),
    [
        ("connect", ConnectMessage),
        ("pending", PendingResponse),
        ("connected", ConnectedResponse),
        ("invoke", InvokeMessage),
        ("result", ResultMessage),
    ],
)
def test_native_node_fixtures(key: str, model: type) -> None:
    fixture = json.loads(FIXTURES.read_text())[key]
    parsed = model.model_validate(fixture)
    assert parsed.type == key
    for field, value in fixture.items():
        assert parsed.model_dump()[field] == value
