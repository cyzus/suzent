"""A folder the user authorized stays authorized across turns and sub-agents.

The working directory used to be read only from the request config, so it
vanished at the next turn boundary, and sub-agents fell back to the project
directory even when the parent was pinned to the user's folder.
"""

from types import SimpleNamespace

import pytest

from suzent.core.subagent_runner import (
    inherited_working_directory,
    persistable_grants,
    resolve_granted_cwd,
)


def _build_deps(
    monkeypatch,
    temp_db,
    tmp_path,
    *,
    working_directory=None,
    chat_config=None,
    config=None,
):
    """Build AgentDeps for a chat persisted with the given grant."""
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    chat_id = temp_db.create_chat("grant test", config=chat_config or {})
    if working_directory is not None:
        temp_db.update_chat(chat_id, working_directory=working_directory)

    from suzent.core.context_injection import build_agent_deps

    base = {
        "sandbox_enabled": False,
        "workspace_root": str(tmp_path / "workspace"),
        "sandbox_data_path": str(tmp_path / "sandbox"),
        "memory_enabled": False,
    }
    return build_agent_deps(
        chat_id=chat_id, user_id="user-1", config={**base, **(config or {})}
    )


@pytest.fixture
def target_folder(tmp_path):
    folder = tmp_path / "Documents" / "project" / "assets"
    (folder / "captions").mkdir(parents=True)
    return folder


def test_working_directory_survives_a_turn_that_omits_it(
    monkeypatch, temp_db, tmp_path, target_folder
):
    deps = _build_deps(
        monkeypatch, temp_db, tmp_path, working_directory=str(target_folder)
    )

    assert deps.cwd == str(target_folder)
    assert deps.path_resolver.get_working_dir() == target_folder.resolve()
    assert deps.path_resolver.resolve(str(target_folder)) == target_folder.resolve()


def test_persisted_chat_config_also_carries_the_grant(
    monkeypatch, temp_db, tmp_path, target_folder
):
    deps = _build_deps(
        monkeypatch, temp_db, tmp_path, chat_config={"cwd": str(target_folder)}
    )

    assert deps.path_resolver.get_working_dir() == target_folder.resolve()


def test_request_config_still_wins_over_the_persisted_value(
    monkeypatch, temp_db, tmp_path, target_folder
):
    other = tmp_path / "Documents" / "other"
    other.mkdir(parents=True)

    deps = _build_deps(
        monkeypatch,
        temp_db,
        tmp_path,
        working_directory=str(other),
        config={"cwd": str(target_folder)},
    )

    assert deps.path_resolver.get_working_dir() == target_folder.resolve()


def test_no_grant_leaves_the_resolver_on_the_project_dir(
    monkeypatch, temp_db, tmp_path
):
    deps = _build_deps(monkeypatch, temp_db, tmp_path)

    assert deps.cwd is None
    assert deps.path_resolver.get_working_dir() == deps.path_resolver.project_dir


@pytest.mark.parametrize(
    "chat, expected",
    [
        (None, None),
        (SimpleNamespace(config={}, working_directory=None), None),
        (SimpleNamespace(config={}, working_directory="/authorized"), "/authorized"),
        (
            SimpleNamespace(config={"cwd": "/from-config"}, working_directory=None),
            "/from-config",
        ),
        (
            SimpleNamespace(
                config={"cwd": "/from-config"}, working_directory="/column"
            ),
            "/column",
        ),
    ],
)
def test_subagent_inherits_the_parent_working_directory(chat, expected):
    assert inherited_working_directory(chat) == expected


def _parent_chat(temp_db, tmp_path, target_folder, volumes=None, sandbox_enabled=False):
    parent_id = temp_db.create_chat(
        "parent",
        config={
            "sandbox_enabled": sandbox_enabled,
            "workspace_root": str(tmp_path / "workspace"),
            "sandbox_volumes": volumes or [],
        },
    )
    temp_db.update_chat(parent_id, working_directory=str(target_folder))
    return temp_db.get_chat(parent_id)


def test_a_sandboxed_subagent_cannot_be_pointed_outside_the_parent_grants(
    monkeypatch, temp_db, tmp_path, target_folder
):
    # cwd on the spawn tool is model-chosen. Under the sandbox the parent's
    # grants are a real boundary, so it must not widen access.
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    parent = _parent_chat(temp_db, tmp_path, target_folder, sandbox_enabled=True)

    assert resolve_granted_cwd(parent, str(target_folder / "captions")) == str(
        (target_folder / "captions").resolve()
    )
    assert (
        resolve_granted_cwd(parent, str(tmp_path / "Documents" / "elsewhere")) is None
    )


def test_a_host_subagent_may_be_pointed_at_any_directory(
    monkeypatch, temp_db, tmp_path, target_folder
):
    # On the host the parent reaches other directories by asking the user, so
    # refusing here would only block delegating work the parent may itself do.
    # The child's own approval prompts stay the gate.
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    parent = _parent_chat(temp_db, tmp_path, target_folder)
    elsewhere = tmp_path / "Documents" / "elsewhere"

    assert resolve_granted_cwd(parent, str(elsewhere)) == str(elsewhere.resolve())


def test_a_subagent_may_be_pinned_by_the_virtual_path_it_can_see(
    monkeypatch, temp_db, tmp_path, target_folder
):
    # The model addresses directories as it sees them, so a mounted volume's
    # virtual path has to resolve to its host path rather than be rejected.
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    volume_root = tmp_path / "Documents" / "library"
    (volume_root / "pkg").mkdir(parents=True)
    parent = _parent_chat(
        temp_db, tmp_path, target_folder, volumes=[f"{volume_root}:/mnt/library"]
    )

    assert resolve_granted_cwd(parent, "/mnt/library/pkg") == str(
        (volume_root / "pkg").resolve()
    )


def test_grants_are_persisted_so_a_later_turn_keeps_the_folder():
    config = {"cwd": "/authorized", "sandbox_volumes": ["/host:/mnt/data"]}

    assert persistable_grants(config, None) == config


def test_a_disposable_worktree_cwd_is_not_persisted():
    # The worktree is removed in _run_subagent's finally block, so a resumed turn
    # would otherwise point at a deleted directory.
    config = {
        "cwd": "/repo/.git/worktrees-tmp/subagent-1",
        "sandbox_volumes": ["/host:/mnt/data"],
    }

    assert persistable_grants(config, "worktree") == {
        "sandbox_volumes": ["/host:/mnt/data"]
    }


def test_an_unrecognized_host_path_is_not_laundered_by_virtual_mapping(
    monkeypatch, temp_db, tmp_path, target_folder
):
    # In sandbox mode an unmatched absolute path falls through to
    # project_dir/<the whole path>, which is inside a grant but is not the
    # directory that was asked for. It must not count as an authorization.
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    parent_id = temp_db.create_chat(
        "parent",
        config={
            "sandbox_enabled": True,
            "workspace_root": str(tmp_path / "workspace"),
            "sandbox_volumes": [],
        },
    )
    temp_db.update_chat(parent_id, working_directory=str(target_folder))
    parent = temp_db.get_chat(parent_id)

    assert resolve_granted_cwd(parent, "/etc") is None
    assert resolve_granted_cwd(parent, str(target_folder)) == str(
        target_folder.resolve()
    )
