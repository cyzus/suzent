import json
from unittest.mock import AsyncMock

import pytest

from suzent.core.providers.base import Model
from suzent.routes import config_routes as routes


class CatalogFallback:
    """A provider whose /models call failed, so it returned catalog defaults."""

    used_catalog_fallback = True

    def __init__(self, discovery_error: str) -> None:
        self.discovery_error = discovery_error

    async def list_models(self) -> list[Model]:
        return [Model(id="p/flagship", name="flagship")]


@pytest.mark.parametrize(
    ("discovery_error", "success"),
    [
        ("The models endpoint returned HTTP 401", False),
        ("The models endpoint returned HTTP 403", False),
        ("The models endpoint returned HTTP 404", True),
    ],
)
async def test_refused_key_is_not_reported_as_connected(
    monkeypatch: pytest.MonkeyPatch, discovery_error: str, success: bool
) -> None:
    monkeypatch.setattr(
        routes.ProviderFactory,
        "get_provider",
        lambda *_: CatalogFallback(discovery_error),
    )
    autofilled: list[list[str]] = []
    monkeypatch.setattr(
        routes,
        "_ensure_provider_roles_autofilled",
        lambda _id, ids: autofilled.append(ids),
    )
    request = AsyncMock()
    request.path_params = {"provider_id": "p"}
    request.json.return_value = {"config": {}}
    body = json.loads((await routes.verify_provider(request)).body)
    assert body["success"] is success
    assert bool(autofilled) is success
