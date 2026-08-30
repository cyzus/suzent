"""A folder the user authorized stays authorized across turns and sub-agents.

The working directory used to be read only from the request config, so it
vanished at the next turn boundary, and sub-agents fell back to the project
directory even when the parent was pinned to the user's folder.
"""

from types import SimpleNamespace

import pytest

from suzent.core.subagent_runner import grants_cover, inherited_working_directory


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


def test_a_subagent_cannot_be_pointed_outside_the_parent_grants(
    monkeypatch, temp_db, tmp_path, target_folder
):
    # cwd on the spawn tool is model-chosen, so it must not widen access.
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    parent_id = temp_db.create_chat(
        "parent",
        config={
            "sandbox_enabled": False,
            "workspace_root": str(tmp_path / "workspace"),
            "sandbox_volumes": [],
        },
    )
    temp_db.update_chat(parent_id, working_directory=str(target_folder))
    parent = temp_db.get_chat(parent_id)

    assert grants_cover(parent, str(target_folder / "captions")) is True
    assert grants_cover(parent, str(tmp_path / "Documents" / "elsewhere")) is False
