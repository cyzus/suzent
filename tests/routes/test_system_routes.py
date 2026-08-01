from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes import system_routes


def test_system_version_reports_running_backend_package(monkeypatch) -> None:
    monkeypatch.setattr(system_routes, "_get_source_version", lambda: None)
    monkeypatch.setattr(system_routes, "package_version", lambda _name: "1.2.3")
    monkeypatch.setattr(system_routes, "get_backend_commit", lambda: "abc123")
    app = Starlette(routes=[Route("/system/version", system_routes.get_system_version)])

    response = TestClient(app).get("/system/version")

    assert response.status_code == 200
    assert response.json() == {
        "backend_version": "1.2.3",
        "api_version": system_routes.API_VERSION,
        "build_commit": "abc123",
        "development_mode": False,
    }


def test_backend_version_falls_back_when_package_metadata_is_missing(
    monkeypatch,
) -> None:
    def missing_package(_name: str) -> str:
        raise system_routes.PackageNotFoundError

    monkeypatch.setattr(system_routes, "package_version", missing_package)
    monkeypatch.setattr(system_routes, "_get_source_version", lambda: None)

    assert system_routes.get_backend_version() == "unknown"


def test_backend_version_prefers_source_checkout(tmp_path, monkeypatch) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "suzent"\nversion = "2.3.4"\n',
        encoding="utf-8",
    )
    source_file = tmp_path / "src" / "suzent" / "routes" / "system_routes.py"
    source_file.parent.mkdir(parents=True)
    source_file.touch()
    source_version = system_routes._get_source_version(source_file)
    monkeypatch.setattr(system_routes, "_get_source_version", lambda: source_version)
    monkeypatch.setattr(system_routes, "package_version", lambda _name: "1.2.3")

    assert system_routes.get_backend_version() == "2.3.4"


def test_backend_commit_prefers_build_environment(monkeypatch) -> None:
    monkeypatch.setenv("SUZENT_BUILD_COMMIT", "release-commit")

    assert system_routes.get_backend_commit() == "release-commit"
