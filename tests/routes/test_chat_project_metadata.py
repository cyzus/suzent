import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.database import ChatDatabase


def test_chat_detail_reports_current_project(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import chat_routes

    monkeypatch.setattr(chat_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(routes=[Route("/chats/{chat_id}", chat_routes.get_chat)])
    )
    chat_id = temp_db.create_chat("Running chat", {})
    project_id = temp_db.create_project("Work", "work")
    temp_db.link_chat_to_project(chat_id, project_id)

    response = client.get(f"/chats/{chat_id}")
    assert response.status_code == 200
    assert response.json()["projectId"] == project_id

    other_project_id = temp_db.create_project("Other", "other")
    temp_db.link_chat_to_project(chat_id, other_project_id)
    assert client.get(f"/chats/{chat_id}").json()["projectId"] == other_project_id


def test_project_unread_counts_include_all_chats_and_follow_moves(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import project_routes

    monkeypatch.setattr(project_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(routes=[Route("/projects", project_routes.list_projects)])
    )
    project_id = temp_db.create_project("Work", "work")
    other_project_id = temp_db.create_project("Other", "other")
    older = temp_db.create_chat("Older", {"unread_count": 2})
    newer = temp_db.create_chat("Newer", {"unread_count": 1})
    temp_db.link_chat_to_project(older, project_id)
    temp_db.link_chat_to_project(newer, project_id)

    def counts() -> dict[str, dict[str, int]]:
        response = client.get("/projects")
        assert response.status_code == 200
        return {p["id"]: p["unreadChatCounts"] for p in response.json()}

    assert counts()[project_id] == {older: 2, newer: 1}
    temp_db.mark_chat_read(older)
    assert counts()[project_id] == {newer: 1}
    temp_db.link_chat_to_project(newer, other_project_id)
    assert counts()[project_id] == {}
    assert counts()[other_project_id] == {newer: 1}


def test_projects_are_listed_most_recently_active_first(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    from suzent.database.models import ChatModel
    from suzent.routes import project_routes

    monkeypatch.setattr(project_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(routes=[Route("/projects", project_routes.list_projects)])
    )
    old_project = temp_db.create_project("Old", "old")
    new_project = temp_db.create_project("New", "new")
    old_chat = temp_db.create_chat("Old chat", {})
    new_chat = temp_db.create_chat("New chat", {})
    temp_db.link_chat_to_project(old_chat, old_project)
    temp_db.link_chat_to_project(new_chat, new_project)

    def touch(chat_id: str, when: datetime) -> None:
        with temp_db._session() as session:
            chat = session.get(ChatModel, chat_id)
            chat.updated_at = when
            session.add(chat)
            session.commit()

    def order() -> list[str]:
        ids = [p["id"] for p in client.get("/projects").json()]
        return [pid for pid in ids if pid in {old_project, new_project}]

    touch(old_chat, datetime(2030, 1, 1))
    touch(new_chat, datetime(2030, 1, 2))
    assert order() == [new_project, old_project]

    touch(old_chat, datetime(2030, 1, 3))
    assert order() == [old_project, new_project]


def test_project_activity_compares_utc_creation_with_local_chat_time(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta, timezone

    from suzent.database.models import ChatModel, ProjectModel
    from suzent.routes import project_routes

    monkeypatch.setattr(project_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(routes=[Route("/projects", project_routes.list_projects)])
    )
    fresh_project = temp_db.create_project("Fresh", "fresh")
    idle_project = temp_db.create_project("Idle", "idle")
    chat_id = temp_db.create_chat("Chat", {})
    temp_db.link_chat_to_project(chat_id, idle_project)

    now_utc = datetime.now(timezone.utc)
    with temp_db._session() as session:
        project = session.get(ProjectModel, fresh_project)
        project.created_at = now_utc.replace(tzinfo=None)
        chat = session.get(ChatModel, chat_id)
        chat.updated_at = (
            (now_utc - timedelta(hours=1)).astimezone().replace(tzinfo=None)
        )
        session.add(project)
        session.add(chat)
        session.commit()

    projects = {p["id"]: p for p in client.get("/projects").json()}
    fresh = datetime.fromisoformat(projects[fresh_project]["lastActivityAt"])
    idle = datetime.fromisoformat(projects[idle_project]["lastActivityAt"])
    assert fresh - idle == timedelta(hours=1)


def test_project_working_directory_can_be_set_and_cleared(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from suzent.routes import project_routes

    monkeypatch.setattr(project_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(
            routes=[
                Route("/projects", project_routes.list_projects),
                Route(
                    "/projects/{project_id}",
                    project_routes.update_project,
                    methods=["PATCH"],
                ),
            ]
        )
    )
    project_id = temp_db.create_project("Work", "work")
    folder = tmp_path / "repo"
    folder.mkdir()

    response = client.patch(
        f"/projects/{project_id}", json={"working_directory": str(folder)}
    )
    assert response.status_code == 200
    assert response.json()["workingDirectory"] == str(folder.resolve())
    listed = {p["id"]: p for p in client.get("/projects").json()}
    assert listed[project_id]["workingDirectory"] == str(folder.resolve())

    missing = client.patch(
        f"/projects/{project_id}",
        json={"working_directory": str(tmp_path / "missing")},
    )
    assert missing.status_code == 400
    relative = client.patch(
        f"/projects/{project_id}", json={"working_directory": "relative/dir"}
    )
    assert relative.status_code == 400
    assert temp_db.get_project(project_id).working_directory == str(folder.resolve())

    cleared = client.patch(f"/projects/{project_id}", json={"working_directory": None})
    assert cleared.status_code == 200
    assert cleared.json()["workingDirectory"] is None


def test_project_folders_list_what_its_chats_used(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from suzent.routes import project_routes

    monkeypatch.setattr(project_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(
            routes=[
                Route(
                    "/projects/{project_id}/folders",
                    project_routes.list_project_folders,
                )
            ]
        )
    )
    project_id = temp_db.create_project("Work", "work")
    other_project_id = temp_db.create_project("Other", "other")
    repo, data, gone, elsewhere = (tmp_path / n for n in ("repo", "data", "gone", "x"))
    for folder in (repo, data, elsewhere):
        folder.mkdir()

    mounted = temp_db.create_chat(
        "mounted",
        {"sandbox_volumes": [f"{data}:/mnt/data", f"{gone}:/mnt/gone"]},
    )
    temp_db.link_chat_to_project(mounted, project_id)
    pinned = temp_db.create_chat("pinned", {})
    temp_db.link_chat_to_project(pinned, project_id)
    temp_db.update_chat(pinned, working_directory=str(repo))
    other = temp_db.create_chat("other", {"cwd": str(elsewhere)})
    temp_db.link_chat_to_project(other, other_project_id)

    response = client.get(f"/projects/{project_id}/folders")
    assert response.status_code == 200
    assert response.json()["folders"] == [str(repo), str(data)]
    assert client.get("/projects/missing/folders").status_code == 404


def test_project_extra_folders_are_mounted_for_its_chats(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from suzent.routes import project_routes

    monkeypatch.setattr(project_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(
            routes=[
                Route(
                    "/projects/{project_id}",
                    project_routes.update_project,
                    methods=["PATCH"],
                )
            ]
        )
    )
    project_id = temp_db.create_project("Work", "work")
    docs, data = tmp_path / "docs", tmp_path / "other" / "docs"
    docs.mkdir()
    data.mkdir(parents=True)

    response = client.patch(
        f"/projects/{project_id}",
        json={"extra_folders": [str(docs), str(data), str(docs)]},
    )
    assert response.status_code == 200
    assert response.json()["extraFolders"] == [str(docs), str(data)]
    assert (
        client.patch(
            f"/projects/{project_id}",
            json={"extra_folders": [str(tmp_path / "missing")]},
        ).status_code
        == 400
    )

    chat_id = temp_db.create_chat("chat", {})
    temp_db.link_chat_to_project(chat_id, project_id)
    chat = temp_db.get_chat(chat_id)
    assert temp_db.with_project_folders(chat, None) == [
        f"{docs}:/mnt/docs",
        f"{data}:/mnt/docs-1",
    ]
    # A folder the chat already mounts keeps the chat's mount.
    assert temp_db.with_project_folders(chat, [f"{docs}:/mnt/mine"]) == [
        f"{docs}:/mnt/mine",
        f"{data}:/mnt/docs",
    ]

    outside = temp_db.create_chat("outside", {})
    assert temp_db.with_project_folders(temp_db.get_chat(outside), ["a:/b"]) == ["a:/b"]
