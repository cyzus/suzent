"""Tests for declarative cron preset installation via ensure_cron_presets."""

from suzent.config import CONFIG
from suzent.core.scheduler import ensure_cron_presets

INGEST_NAME = "wiki-ingest-daily"
LINT_NAME = "wiki-lint-weekly"


def _wiki_presets():
    return [
        {
            "name": INGEST_NAME,
            "cron_expr": "0 2 * * *",
            "prompt": "Run ingest.",
            "delivery_mode": "announce",
            "requires": "wiki_enabled",
        },
        {
            "name": LINT_NAME,
            "cron_expr": "0 3 * * 0",
            "prompt": "Run lint.",
            "delivery_mode": "announce",
            "requires": "wiki_enabled",
        },
    ]


def test_ensure_cron_presets_creates_jobs(temp_db, monkeypatch):
    monkeypatch.setattr(CONFIG, "wiki_enabled", True)
    monkeypatch.setattr(CONFIG, "cron_presets", _wiki_presets())

    result = ensure_cron_presets(temp_db)

    assert result["success"] is True
    assert sorted(result["created"]) == [INGEST_NAME, LINT_NAME]
    assert result["updated"] == []
    assert result["skipped"] == []

    names = {job.name for job in temp_db.list_cron_jobs()}
    assert INGEST_NAME in names
    assert LINT_NAME in names


def test_ensure_cron_presets_is_idempotent(temp_db, monkeypatch):
    monkeypatch.setattr(CONFIG, "wiki_enabled", True)
    monkeypatch.setattr(CONFIG, "cron_presets", _wiki_presets())

    first = ensure_cron_presets(temp_db)
    second = ensure_cron_presets(temp_db)

    assert first["success"] is True
    assert second["created"] == []
    assert sorted(second["unchanged"]) == [INGEST_NAME, LINT_NAME]


def test_ensure_cron_presets_skips_when_requires_is_falsy(temp_db, monkeypatch):
    monkeypatch.setattr(CONFIG, "wiki_enabled", False)
    monkeypatch.setattr(CONFIG, "cron_presets", _wiki_presets())

    result = ensure_cron_presets(temp_db)

    assert result["success"] is True
    assert result["created"] == []
    assert sorted(result["skipped"]) == [INGEST_NAME, LINT_NAME]
    assert temp_db.list_cron_jobs() == []


def test_ensure_cron_presets_skips_when_enabled_false(temp_db, monkeypatch):
    presets = _wiki_presets()
    for p in presets:
        p["enabled"] = False
    monkeypatch.setattr(CONFIG, "wiki_enabled", True)
    monkeypatch.setattr(CONFIG, "cron_presets", presets)

    result = ensure_cron_presets(temp_db)

    assert sorted(result["skipped"]) == [INGEST_NAME, LINT_NAME]
    assert result["created"] == []


def test_ensure_cron_presets_updates_stale_jobs(temp_db, monkeypatch):
    monkeypatch.setattr(CONFIG, "wiki_enabled", True)
    monkeypatch.setattr(CONFIG, "cron_presets", _wiki_presets())

    # Seed an existing job with a stale cron_expr and prompt.
    ingest_id = temp_db.create_cron_job(
        name=INGEST_NAME,
        cron_expr="*/15 * * * *",
        prompt="old prompt",
        active=True,
        delivery_mode="silent",
    )
    assert ingest_id is not None

    result = ensure_cron_presets(temp_db)

    assert INGEST_NAME in result["updated"]
    job = next(j for j in temp_db.list_cron_jobs() if j.name == INGEST_NAME)
    assert job.cron_expr == "0 2 * * *"
    assert job.prompt == "Run ingest."
    assert job.delivery_mode == "announce"


def test_ensure_cron_presets_can_activate_existing(temp_db, monkeypatch):
    monkeypatch.setattr(CONFIG, "wiki_enabled", True)
    monkeypatch.setattr(CONFIG, "cron_presets", _wiki_presets())

    ingest_id = temp_db.create_cron_job(
        name=INGEST_NAME,
        cron_expr="0 2 * * *",
        prompt="Run ingest.",
        active=False,
        delivery_mode="announce",
    )
    assert ingest_id is not None

    # Without activate_existing — should not flip the active flag.
    ensure_cron_presets(temp_db, activate_existing=False)
    job = next(j for j in temp_db.list_cron_jobs() if j.name == INGEST_NAME)
    assert job.active is False

    # With activate_existing — should flip it.
    ensure_cron_presets(temp_db, activate_existing=True)
    job_after = next(j for j in temp_db.list_cron_jobs() if j.name == INGEST_NAME)
    assert job_after.active is True


def test_ensure_cron_presets_empty_list(temp_db, monkeypatch):
    monkeypatch.setattr(CONFIG, "cron_presets", [])

    result = ensure_cron_presets(temp_db)

    assert result["success"] is True
    assert result["created"] == []
