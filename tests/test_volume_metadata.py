from pathlib import Path
from types import SimpleNamespace

from suzent.core.volume_metadata import probe_volume_metadata, refresh_volume_metadata
from suzent.prompts import build_custom_volumes_section


def test_notebook_volume_metadata_skips_git_probe(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("notebook volumes should not be Git-probed")

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)

    metadata = probe_volume_metadata("C:/Users/example/Notebook:/mnt/notebook")

    assert metadata["kind"] == "notebook"
    assert metadata["is_git_repo"] is None
    assert calls == []


def test_generic_volume_records_git_root(monkeypatch):
    host_path = Path.cwd()

    class Result:
        returncode = 0
        stdout = str(host_path)

    def fake_run(*args, **kwargs):
        return Result()

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)

    metadata = probe_volume_metadata(f"{host_path}:/mnt/project")

    assert metadata["kind"] == "generic"
    assert metadata["exists"] is True
    assert metadata["is_git_repo"] is True
    assert metadata["git_root"] == str(host_path)
    assert metadata["status"] == "ok"


def test_refresh_volume_metadata_persists_to_database(temp_db):
    volume = f"{Path.cwd()}:/mnt/project"

    refresh_volume_metadata(temp_db, [volume])

    metadata = temp_db.get_volume_metadata([volume])

    assert volume in metadata
    assert metadata[volume]["exists"] is True


def test_prompt_uses_cached_volume_metadata():
    host_path = Path.cwd()
    volume = f"{host_path}:/mnt/project"
    deps = SimpleNamespace(
        custom_volumes=[volume],
        custom_volume_metadata={
            volume: {
                "kind": "generic",
                "status": "ok",
                "is_git_repo": True,
                "git_root": str(host_path),
            }
        },
    )

    section = build_custom_volumes_section(deps)

    assert "Git repo: Yes" in section
    assert str(host_path) in section
