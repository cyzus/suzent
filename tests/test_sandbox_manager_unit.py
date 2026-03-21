"""Unit tests for Docker sandbox manager internals."""

from __future__ import annotations

from suzent.sandbox.manager import DockerSession, SandboxManager


class _FakeContainers:
    def list(self, **kwargs):
        return []


class _FakeDockerClient:
    def __init__(self):
        self.containers = _FakeContainers()

    def ping(self):
        return True

    def close(self):
        return None


def test_docker_session_process_id_validation_accepts_hex12():
    assert DockerSession._validate_proc_id("a1b2c3d4e5f6") == "a1b2c3d4e5f6"


def test_docker_session_process_id_validation_rejects_invalid_values():
    invalid = ["", "abc", "G1b2c3d4e5f6", "a1b2c3d4e5f6x", "../evil", "a1b2-c3d4"]
    for value in invalid:
        try:
            DockerSession._validate_proc_id(value)
            assert False, f"expected ValueError for {value!r}"
        except ValueError:
            pass


def test_sandbox_manager_singleton_per_volume_key(monkeypatch):
    import suzent.sandbox.manager as manager_mod

    monkeypatch.setattr(manager_mod, "_manager_singletons", {})
    monkeypatch.setattr(SandboxManager, "_start_idle_cleanup_thread", lambda self: None)
    monkeypatch.setattr(SandboxManager, "_cleanup_orphans", lambda self: None)

    import docker

    monkeypatch.setattr(docker, "from_env", lambda: _FakeDockerClient())

    m1 = SandboxManager(custom_volumes=["/host/a:/mnt/a", "/host/b:/mnt/b"])
    m2 = SandboxManager(custom_volumes=["/host/b:/mnt/b", "/host/a:/mnt/a"])
    m3 = SandboxManager(custom_volumes=["/host/c:/mnt/c"])

    assert m1 is m2
    assert m1 is not m3
