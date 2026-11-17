from __future__ import annotations

import pytest

from suzent.core import model_catalog_cache as cache


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    cache.invalidate_model_catalog()


def test_catalog_is_cached_per_backend_and_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    clock = [0.0]
    monkeypatch.setattr(cache, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "suzent.core.providers.get_enabled_models_from_db",
        lambda: calls.append("models") or ["p/m"],
    )
    monkeypatch.setattr(
        "suzent.core.providers.get_starred_models_from_db",
        lambda: calls.append("stars") or ["p/m", "removed/model"],
    )
    owner = object()
    first = cache.get_model_catalog(owner)
    assert cache.get_model_catalog(owner) is first
    assert first.starred == ("p/m",)
    assert calls == ["models", "stars"]
    clock[0] = cache.CATALOG_TTL_SECONDS
    assert cache.get_model_catalog(owner) is not first
    assert len(calls) == 4
    cache.get_model_catalog(object())
    assert len(calls) == 6


def test_configuration_invalidation_immediately_rebuilds_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = ["p/old"]
    monkeypatch.setattr(
        "suzent.core.providers.get_enabled_models_from_db", lambda: models.copy()
    )
    monkeypatch.setattr("suzent.core.providers.get_starred_models_from_db", lambda: [])
    owner = object()
    assert cache.get_model_catalog(owner).models == ("p/old",)
    models[:] = ["p/new"]
    from suzent.core.providers import invalidate_default_model_cache

    invalidate_default_model_cache()
    assert cache.get_model_catalog(owner).models == ("p/new",)


def test_invalidation_during_load_does_not_publish_stale_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def models() -> list[str]:
        calls.append(True)
        if len(calls) == 1:
            cache.invalidate_model_catalog()
            return ["p/stale"]
        return ["p/current"]

    monkeypatch.setattr("suzent.core.providers.get_enabled_models_from_db", models)
    monkeypatch.setattr("suzent.core.providers.get_starred_models_from_db", lambda: [])
    owner = object()
    assert cache.get_model_catalog(owner).models == ("p/current",)
    assert len(calls) == 2
    assert cache.get_model_catalog(owner).models == ("p/current",)
    assert len(calls) == 2
