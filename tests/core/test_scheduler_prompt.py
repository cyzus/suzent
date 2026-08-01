"""Tests for the prompt context supplied to cron-triggered turns."""

from datetime import datetime, timedelta, timezone

from suzent.core.scheduler import build_cron_reminder


def test_build_cron_reminder_includes_trigger_context_and_local_time():
    pacific_time = timezone(timedelta(hours=-7), name="PDT")
    triggered_at = datetime(2026, 8, 1, 9, 30, 45, tzinfo=pacific_time)

    reminder = build_cron_reminder(
        "daily-summary",
        "Summarize today's agenda.",
        triggered_at=triggered_at,
        last_run_at=datetime(2026, 7, 31, 9, 30, 45, tzinfo=pacific_time),
    )

    assert reminder == (
        "**Scheduled Task: daily-summary**\n\n"
        "You were automatically woken by the cron scheduler.\n"
        "Current local time: 2026-08-01T09:30:45-07:00 (PDT, UTC-07:00)\n\n"
        "Last run: 2026-07-31T09:30:45-07:00\n\n"
        "Summarize today's agenda."
    )


def test_build_cron_reminder_assigns_local_timezone_to_naive_time():
    reminder = build_cron_reminder(
        "local-task", "Run it.", triggered_at=datetime(2026, 8, 1, 9, 30)
    )

    assert "Current local time: 2026-08-01T09:30:00" in reminder
    assert "UTC offset unknown" not in reminder
    assert "Last run: none (first run)" in reminder
