from __future__ import annotations

import json
import os
import time

import psutil
import pytest

from suzent.service import state as service_state
from suzent.service.state import ServiceInstanceLock, read_process_state


@pytest.fixture
def isolated_service_state(tmp_path, monkeypatch):
    monkeypatch.setattr(service_state, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(service_state, "SERVICE_STATE_PATH", tmp_path / "service.json")
    monkeypatch.setattr(service_state, "SERVICE_LOCK_PATH", tmp_path / "service.lock")
    return tmp_path


def test_service_lock_persists_exact_process_identity(isolated_service_state):
    lock = ServiceInstanceLock(port=25314)

    persisted = lock.acquire()

    assert persisted.pid == os.getpid()
    assert len(persisted.control_token) >= 32
    assert persisted.process_created_at == pytest.approx(
        psutil.Process().create_time(), abs=1.0
    )
    assert read_process_state() == persisted

    lock.release()
    assert read_process_state() is None
    assert not service_state.SERVICE_LOCK_PATH.exists()
    assert not service_state.SERVICE_STATE_PATH.exists()


def test_service_lock_rejects_second_live_instance(isolated_service_state):
    first = ServiceInstanceLock()
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            ServiceInstanceLock().acquire()
    finally:
        first.release()


def test_service_lock_replaces_stale_files(isolated_service_state):
    service_state.SERVICE_LOCK_PATH.write_text("stale", encoding="ascii")
    old = time.time() - service_state.LOCK_STARTUP_GRACE_SECONDS - 1
    os.utime(service_state.SERVICE_LOCK_PATH, (old, old))
    service_state.SERVICE_STATE_PATH.write_text(
        json.dumps(
            {
                "instance_id": "stale",
                "control_token": "stale-token",
                "pid": 99999999,
                "process_created_at": 1,
                "started_at": "2026-01-01T00:00:00+00:00",
                "port": 25314,
                "version": "0.0.0",
            }
        ),
        encoding="utf-8",
    )

    lock = ServiceInstanceLock()
    state = lock.acquire()
    try:
        assert state.instance_id != "stale"
        assert read_process_state() == state
    finally:
        lock.release()


def test_service_lock_preserves_a_fresh_startup_lock(isolated_service_state):
    service_state.SERVICE_LOCK_PATH.write_text("starting", encoding="ascii")

    with pytest.raises(RuntimeError, match="still starting"):
        ServiceInstanceLock().acquire()

    assert service_state.SERVICE_LOCK_PATH.read_text(encoding="ascii") == "starting"
    assert not service_state.SERVICE_STATE_PATH.exists()


def test_release_does_not_remove_another_instances_files(isolated_service_state):
    lock = ServiceInstanceLock()
    lock.acquire()
    service_state.SERVICE_LOCK_PATH.write_text("replacement", encoding="ascii")
    service_state.SERVICE_STATE_PATH.write_text(
        json.dumps({"instance_id": "replacement"}), encoding="utf-8"
    )

    lock.release()

    assert service_state.SERVICE_LOCK_PATH.exists()
    assert service_state.SERVICE_STATE_PATH.exists()
