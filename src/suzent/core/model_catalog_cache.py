"""Cache public model IDs, never credentials or per-device permissions."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic

CATALOG_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class ModelCatalog:
    models: tuple[str, ...]
    starred: tuple[str, ...]


@dataclass(frozen=True)
class _Entry:
    owner: object
    catalog: ModelCatalog
    expires: float


_lock = Lock()
_entry: _Entry | None = None
_revision = 0


def invalidate_model_catalog() -> None:
    global _entry, _revision
    with _lock:
        _entry = None
        _revision += 1


def get_model_catalog(owner: object) -> ModelCatalog:
    global _entry
    from suzent.core.providers import (
        get_enabled_models_from_db,
        get_starred_models_from_db,
    )

    while True:
        with _lock:
            if (
                _entry is not None
                and _entry.owner is owner
                and monotonic() < _entry.expires
            ):
                return _entry.catalog
            revision = _revision
        # Credential/file reads must not hold the invalidation lock across I/O.
        models = tuple(get_enabled_models_from_db())
        available = set(models)
        catalog = ModelCatalog(
            models,
            tuple(
                model for model in get_starred_models_from_db() if model in available
            ),
        )
        with _lock:
            if revision != _revision:
                continue
            _entry = _Entry(owner, catalog, monotonic() + CATALOG_TTL_SECONDS)
            return catalog
