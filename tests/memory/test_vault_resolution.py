"""The vault the app uses is often not the one `CONFIG.notebook_dir` names.

Mounting your own folder at `/mnt/notebook` maps the agent's side of the sandbox;
`CONFIG.notebook_dir` keeps pointing at the default under the data dir, which still
gets created and bootstrapped. Reading it directly means reading a stale skeleton and
concluding the vault is nearly empty — which is exactly the mistake this resolver
exists to prevent.
"""

from pathlib import Path

from suzent.memory.lifecycle import resolve_notebook_dir


def test_a_mounted_vault_wins_over_the_configured_default(monkeypatch, tmp_path):
    mounted = tmp_path / "obsidian" / "vault"
    mounted.mkdir(parents=True)
    monkeypatch.setattr(
        "suzent.memory.lifecycle.CONFIG.sandbox_volumes",
        [f"{mounted}:/mnt/notebook"],
        raising=False,
    )

    assert Path(resolve_notebook_dir()) == mounted.resolve()


def test_other_mounts_are_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "suzent.memory.lifecycle.CONFIG.sandbox_volumes",
        [f"{tmp_path}:/mnt/skills", f"{tmp_path}:/mnt/data"],
        raising=False,
    )
    monkeypatch.setattr(
        "suzent.memory.lifecycle.CONFIG.notebook_dir", str(tmp_path / "default")
    )

    assert Path(resolve_notebook_dir()) == (tmp_path / "default").resolve()


def test_no_mounts_falls_back_to_the_configured_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "suzent.memory.lifecycle.CONFIG.sandbox_volumes", [], raising=False
    )
    monkeypatch.setattr(
        "suzent.memory.lifecycle.CONFIG.notebook_dir", str(tmp_path / "default")
    )

    assert Path(resolve_notebook_dir()) == (tmp_path / "default").resolve()
