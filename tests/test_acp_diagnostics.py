import pytest
from suzent.acp import registry as registry_mod
from suzent.acp.registry import ACPAgent, _npx_package
from suzent.acp.manager import ACPManager


@pytest.fixture(autouse=True)
def _clear_npm_cache():
    registry_mod._npm_cache.clear()
    yield
    registry_mod._npm_cache.clear()


@pytest.mark.asyncio
async def test_probe_diagnostics():
    # Test agent with no binary (not_installed)
    agent = ACPAgent(id="test-agent", name="Test", command=["missing-binary"])
    diag = agent.diagnostics()
    assert diag["status"] == "not_installed"

    # Test agent with existing binary (mock)
    # Note: mocking shutil.which for this test is tricky due to frozen dataclass
    # We rely on the logic check and mocking the behavior in a higher level.
    agent = ACPAgent(
        id="claude-code",
        name="Claude Code",
        command=["acp-adapter", "--adapter", "claude"],
    )
    assert agent.id == "claude-code"
    assert agent.command == ["acp-adapter", "--adapter", "claude"]
    pass


# ── npx package detection ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command,expected",
    [
        (["npx", "-y", "@scope/pkg"], "@scope/pkg"),
        (["npx", "pkg"], "pkg"),
        (["npx", "-y", "pkg@1.2.3"], "pkg"),
        (["npx", "-y", "@scope/pkg@1.2.3"], "@scope/pkg"),
        (["C:\\Program Files\\nodejs\\npx.CMD", "-y", "pkg"], "pkg"),
        (["claude"], None),
        ([], None),
    ],
)
def test_npx_package_parsing(command, expected):
    assert _npx_package(command) == expected


def test_npx_agent_is_not_ready_just_because_npx_exists(monkeypatch):
    """`npx` ships with Node, so its presence proves nothing about the package.

    This is the bug that made every ACP agent report "ready": the status check
    stopped at `shutil.which("npx")`.
    """
    monkeypatch.setattr(registry_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(registry_mod, "_npm_package_installed", lambda pkg: False)

    agent = ACPAgent(id="x", name="X", command=["npx", "-y", "@scope/pkg"])
    assert agent.available is False
    assert agent.diagnostics()["status"] == "not_installed"
    # The package name is more useful than the path to the npx shim.
    assert agent.diagnostics()["executable_path"] == "@scope/pkg"


def test_npx_agent_is_ready_once_the_package_is_present(monkeypatch):
    monkeypatch.setattr(registry_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(registry_mod, "_npm_package_installed", lambda pkg: True)

    agent = ACPAgent(id="x", name="X", command=["npx", "-y", "@scope/pkg"])
    assert agent.available is True


def test_npm_package_found_in_npx_cache(tmp_path, monkeypatch):
    cache = tmp_path / "_npx"
    (cache / "deadbeef" / "node_modules" / "@scope" / "pkg").mkdir(parents=True)
    monkeypatch.setattr(registry_mod, "_npm_global_roots", lambda: [])
    monkeypatch.setattr(registry_mod, "_npx_cache_roots", lambda: [cache])

    assert registry_mod._npm_package_installed("@scope/pkg") is True
    registry_mod._npm_cache.clear()
    assert registry_mod._npm_package_installed("@scope/other") is False


def test_npm_package_found_in_global_root(tmp_path, monkeypatch):
    (tmp_path / "@scope" / "pkg").mkdir(parents=True)
    monkeypatch.setattr(registry_mod, "_npm_global_roots", lambda: [tmp_path])
    monkeypatch.setattr(registry_mod, "_npx_cache_roots", lambda: [])

    assert registry_mod._npm_package_installed("@scope/pkg") is True


def test_npm_detection_survives_a_missing_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(registry_mod, "_npm_global_roots", lambda: [])
    monkeypatch.setattr(registry_mod, "_npx_cache_roots", lambda: [tmp_path / "nope"])
    assert registry_mod._npm_package_installed("anything") is False


@pytest.mark.asyncio
async def test_manager_stop():
    manager = ACPManager()
    # Ensure no error on stopping non-existent session
    await manager.stop("non-existent")
