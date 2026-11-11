from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent import version as suzent_version
from suzent.routes import system_routes


def test_system_version_reports_running_backend_package(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(suzent_version, "_get_source_version", lambda: None)
    monkeypatch.setattr(suzent_version, "package_version", lambda _name: "1.2.3")
    monkeypatch.setattr(system_routes, "get_backend_commit", lambda: "abc123")
    monkeypatch.setattr(system_routes, "get_build_source", lambda: "ci")
    monkeypatch.setattr(system_routes, "get_runtime_kind", lambda: "source")
    monkeypatch.setattr(system_routes, "get_backend_source_root", lambda: tmp_path)
    monkeypatch.setattr(system_routes, "_installation_id", lambda: "a" * 32)
    monkeypatch.setattr(
        "suzent.config.get_data_dir", lambda: tmp_path / "data", raising=False
    )
    # get_system_identity imports get_data_dir locally from suzent.config
    import suzent.config as config

    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path / "data")
    app = Starlette(routes=[Route("/system/version", system_routes.get_system_version)])

    response = TestClient(app).get("/system/version")

    assert response.status_code == 200
    assert response.json() == {
        "backend_version": "1.2.3",
        "api_version": system_routes.API_VERSION,
        "build_commit": "abc123",
        "development_mode": False,
        "build_source": "ci",
        "runtime": "source",
        "installation_id": "a" * 32,
        "data_dir": str(tmp_path / "data"),
        "source_root": str(tmp_path),
    }


def test_backend_version_falls_back_when_package_metadata_is_missing(
    monkeypatch,
) -> None:
    def missing_package(_name: str) -> str:
        raise suzent_version.PackageNotFoundError

    monkeypatch.setattr(suzent_version, "package_version", missing_package)
    monkeypatch.setattr(suzent_version, "_get_source_version", lambda: None)

    assert system_routes.get_backend_version() == "unknown"


def test_backend_version_prefers_source_checkout(tmp_path, monkeypatch) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "suzent"\nversion = "2.3.4"\n',
        encoding="utf-8",
    )
    source_file = tmp_path / "src" / "suzent" / "version.py"
    source_file.parent.mkdir(parents=True)
    source_file.touch()
    source_version = suzent_version._get_source_version(source_file)
    monkeypatch.setattr(suzent_version, "_get_source_version", lambda: source_version)
    monkeypatch.setattr(suzent_version, "package_version", lambda _name: "1.2.3")

    assert system_routes.get_backend_version() == "2.3.4"


def test_backend_commit_prefers_build_environment(monkeypatch) -> None:
    monkeypatch.setenv("SUZENT_BUILD_COMMIT", "release-commit")

    assert system_routes.get_backend_commit() == "release-commit"


def test_backend_commit_reads_symbolic_head_without_spawning_git(
    tmp_path, monkeypatch
) -> None:
    commit = "a" * 40
    git_dir = tmp_path / ".git"
    ref = git_dir / "refs" / "heads" / "main"
    ref.parent.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    ref.write_text(f"{commit}\n", encoding="utf-8")
    source_file = tmp_path / "src" / "suzent" / "routes" / "system_routes.py"
    source_file.parent.mkdir(parents=True)
    source_file.touch()
    monkeypatch.delenv("SUZENT_BUILD_COMMIT", raising=False)
    monkeypatch.setattr(
        system_routes.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("git subprocess must not be started")
        ),
    )

    assert system_routes.get_backend_commit(source_file) == commit


def test_backend_commit_reads_packed_ref(tmp_path, monkeypatch) -> None:
    commit = "b" * 40
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "packed-refs").write_text(
        f"# pack-refs with: peeled fully-peeled sorted\n{commit} refs/heads/main\n",
        encoding="utf-8",
    )
    source_file = tmp_path / "system_routes.py"
    source_file.touch()
    monkeypatch.delenv("SUZENT_BUILD_COMMIT", raising=False)

    assert system_routes.get_backend_commit(source_file) == commit


def test_backend_commit_returns_unknown_for_invalid_metadata(
    tmp_path, monkeypatch
) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("not-a-commit\n", encoding="utf-8")
    source_file = tmp_path / "system_routes.py"
    source_file.touch()
    monkeypatch.delenv("SUZENT_BUILD_COMMIT", raising=False)

    assert system_routes.get_backend_commit(source_file) == "unknown"


def test_build_source_prefers_ci_commit_env(monkeypatch) -> None:
    monkeypatch.setenv("SUZENT_BUILD_COMMIT", "deadbeef")
    monkeypatch.delenv("SUZENT_DEV_MODE", raising=False)

    assert suzent_version.get_build_source() == "ci"


def test_runtime_kind_marks_packaged_builds(monkeypatch) -> None:
    monkeypatch.setenv("SUZENT_PACKAGED", "1")

    assert suzent_version.get_runtime_kind() == "bundled"


def test_runtime_kind_marks_source_checkouts(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SUZENT_PACKAGED", raising=False)
    monkeypatch.delenv("SUZENT_PROJECT_DIR", raising=False)
    monkeypatch.setattr(suzent_version, "get_backend_source_root", lambda: tmp_path)

    assert suzent_version.get_runtime_kind() == "source"


class _WorkspaceResolver:
    def __init__(self, root) -> None:
        self.root = root

    def resolve(self, path: str):
        return self.root / path.removeprefix("/workspace/")


def _host_path_client(monkeypatch, tmp_path) -> TestClient:
    from suzent.routes import sandbox_routes

    monkeypatch.setattr(
        sandbox_routes,
        "_get_resolver_for_request",
        lambda _chat_id: _WorkspaceResolver(tmp_path),
    )
    app = Starlette(
        routes=[Route("/system/host_path", system_routes.host_path, methods=["POST"])]
    )
    return TestClient(app)


def test_host_path_resolves_a_virtual_path_to_the_file_on_disk(
    monkeypatch, tmp_path
) -> None:
    report = tmp_path / "artifacts" / "report.md"
    report.parent.mkdir()
    report.write_text("hi")

    response = _host_path_client(monkeypatch, tmp_path).post(
        "/system/host_path",
        json={"path": "/workspace/artifacts/report.md", "chat_id": "c1"},
    )

    assert response.status_code == 200
    assert response.json() == {"path": str(report)}


def test_host_path_rejects_missing_and_empty_paths(monkeypatch, tmp_path) -> None:
    client = _host_path_client(monkeypatch, tmp_path)

    missing = client.post(
        "/system/host_path", json={"path": "/workspace/gone.md", "chat_id": "c1"}
    )
    empty = client.post("/system/host_path", json={"path": " ", "chat_id": "c1"})

    assert missing.status_code == 404
    assert empty.status_code == 400
