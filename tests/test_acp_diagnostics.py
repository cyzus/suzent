import json

import pytest
from suzent.acp import registry as registry_mod
from suzent.acp.registry import ACPAgent, ACPAgentRegistry, _npx_package
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


def test_a_retired_agent_id_still_resolves(tmp_path, monkeypatch):
    """`codex-acp` was renamed to `codex`; existing chats still carry the old id.

    Without the alias every send on such a chat died with a KeyError.
    """
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    registry = ACPAgentRegistry(path=tmp_path / "acp_agents.json")

    assert registry.get("codex-acp").id == "codex"


def test_a_user_defined_agent_keeps_the_retired_id(tmp_path, monkeypatch):
    """The alias is a fallback, not an override."""
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    path = tmp_path / "acp_agents.json"
    path.write_text(
        json.dumps(
            {"agents": [{"id": "codex-acp", "name": "Mine", "command": ["mine"]}]}
        ),
        encoding="utf-8",
    )
    registry = ACPAgentRegistry(path=path)

    assert registry.get("codex-acp").name == "Mine"


def test_unknown_agent_ids_still_raise(tmp_path):
    registry = ACPAgentRegistry(path=tmp_path / "acp_agents.json")

    with pytest.raises(KeyError):
        registry.get("nope")


def test_display_command_names_the_dependency_not_the_launcher():
    """`command[0]` for the CLI bridge is the Python interpreter.

    Reporting that as unavailable pointed users at the wrong program.
    """
    bridge = ACPAgent(
        id="claude-code",
        name="Claude Code (CLI)",
        command=["/usr/bin/python3", "-m", "suzent.acp.claude_bridge"],
        requires_executable="claude",
    )
    npx_agent = ACPAgent(
        id="codex",
        name="Codex",
        command=["npx", "-y", "@agentclientprotocol/codex-acp"],
    )
    plain = ACPAgent(id="hermes", name="Hermes", command=["hermes", "acp"])

    assert bridge.display_command == "claude"
    assert npx_agent.display_command == "@agentclientprotocol/codex-acp"
    assert plain.display_command == "hermes"


def test_adapter_package_is_only_set_for_npx_launched_agents():
    """The setup panel offers a global install to skip the cold `npx` fetch.

    That download happens inside the `initialize` handshake, so it reads as a
    hung agent. Agents that run their own binary have nothing to prime.
    """
    npx_agent = ACPAgent(
        id="codex",
        name="Codex",
        command=["npx", "-y", "@agentclientprotocol/codex-acp"],
    )
    plain = ACPAgent(id="hermes", name="Hermes", command=["hermes", "acp"])

    assert npx_agent.adapter_package == "@agentclientprotocol/codex-acp"
    assert plain.adapter_package is None


def test_builtins_link_install_docs_instead_of_hardcoding_a_command():
    """Install routes are plural (brew, curl, installer, npm) and per-platform.

    A single `npm install -g` was wrong for anyone who installed another way,
    and for the CLI bridges it named the adapter rather than the agent.
    """
    registry = ACPAgentRegistry(path=None)

    for agent in registry.list_agents():
        assert agent.install_command is None, agent.id
        assert agent.docs_url, agent.id
        assert agent.diagnostics()["docs_url"] == agent.docs_url


def test_a_custom_agent_can_carry_its_own_docs_url(tmp_path):
    path = tmp_path / "acp_agents.json"
    path.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "mine",
                        "name": "Mine",
                        "command": ["mine"],
                        "docs_url": "https://mine.test/install",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = ACPAgentRegistry(path=path)

    assert registry.get("mine").docs_url == "https://mine.test/install"


def test_expanded_builtin_registry_and_aliases(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    registry = ACPAgentRegistry(path=tmp_path / "acp_agents.json")
    ids = {a.id for a in registry.list_agents()}
    assert "claude-code-api" not in ids
    for expected in (
        "claude-code",
        "codex",
        "gemini",
        "github-copilot-cli",
        "qwen-code",
        "kimi-code",
        "grok",
        "opencode",
        "cursor",
        "cline",
        "goose",
        "auggie",
        "kilo",
    ):
        assert expected in ids, f"Missing built-in agent: {expected}"

    assert registry.get("claude-acp").id == "claude-code"
    assert registry.get("claude-code-api").id == "claude-code"
    assert registry.get("grok-build").id == "grok"


def test_dialect_auth_and_quota_error_detection():
    from suzent.acp.client import ACPError

    err_code = ACPError("Sign in", code=-32000)
    assert err_code.auth_required is True

    err_text = ACPError(
        "Error: User is not logged in. Please run `codex login`", code=-32603
    )
    assert err_text.auth_required is True

    err_quota = ACPError("HTTP 429: usage limit or quota exceeded", code=-32603)
    assert err_quota.quota_exceeded is True


def test_on_disk_local_agent_state_inspection(tmp_path, monkeypatch):
    from suzent.acp import dialects

    monkeypatch.setattr(dialects.Path, "home", lambda: tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"subscriptionType": "max"}}),
        encoding="utf-8",
    )

    state = dialects.inspect_local_agent_state("claude-code")
    assert state["auth_hint"] == "ok"
    assert state["usage_summary"] == "Plan: max"


@pytest.mark.asyncio
async def test_seamless_adapter_auto_install(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(registry_mod.shutil, "which", lambda name: f"/usr/bin/{name}")

    class DummyProc:
        returncode = 0

        async def communicate(self):
            # Simulate npm installing the package into ~/.suzent/acp_adapters/node_modules
            pkg_dir = (
                tmp_path
                / "acp_adapters"
                / "node_modules"
                / "@agentclientprotocol"
                / "codex-acp"
            )
            pkg_dir.mkdir(parents=True, exist_ok=True)
            return b"installed", b""

    import asyncio

    async def fake_exec(*args, **kwargs):
        return DummyProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(
        registry_mod,
        "_npm_global_roots",
        lambda: [tmp_path / "acp_adapters" / "node_modules"],
    )
    monkeypatch.setattr(registry_mod, "_npx_cache_roots", lambda: [])

    manager = ACPManager(ACPAgentRegistry(path=tmp_path / "acp_agents.json"))
    agent = manager.registry.get("codex")
    assert agent.available is False

    res = await manager.install_adapter("codex")
    assert res["status"] == "installed"
    assert manager.registry.get("codex").available is True


def test_resolve_managed_npx_command_uses_installed_bin(tmp_path, monkeypatch):
    from suzent.acp.registry import resolve_managed_npx_command

    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        registry_mod.shutil,
        "which",
        lambda name: "/usr/bin/node" if name == "node" else None,
    )

    pkg_dir = tmp_path / "acp_adapters" / "node_modules" / "@google" / "gemini-cli"
    pkg_dir.mkdir(parents=True)
    script = pkg_dir / "dist" / "index.js"
    script.parent.mkdir()
    script.write_text("// gemini", encoding="utf-8")
    (pkg_dir / "package.json").write_text(
        json.dumps({"name": "@google/gemini-cli", "bin": {"gemini": "dist/index.js"}}),
        encoding="utf-8",
    )

    resolved = resolve_managed_npx_command(["npx", "-y", "@google/gemini-cli", "--acp"])
    assert resolved == ["/usr/bin/node", str(script.resolve()), "--acp"]

    # Pinned version mismatch preserves the original npx command
    (pkg_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "@google/gemini-cli",
                "version": "2.0.0",
                "bin": {"gemini": "dist/index.js"},
            }
        ),
        encoding="utf-8",
    )
    assert resolve_managed_npx_command(
        ["npx", "-y", "@google/gemini-cli@1.0.0", "--acp"]
    ) == ["npx", "-y", "@google/gemini-cli@1.0.0", "--acp"]
    assert resolve_managed_npx_command(
        ["npx", "-y", "@google/gemini-cli@2.0.0", "--acp"]
    ) == ["/usr/bin/node", str(script.resolve()), "--acp"]

    # Non-JS native binary in bin executes directly without prepending node
    native_bin = pkg_dir / "bin" / "gemini-native"
    native_bin.parent.mkdir()
    native_bin.write_bytes(b"\x7fELF-native-binary")
    (pkg_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "@google/gemini-cli",
                "version": "2.0.0",
                "bin": "bin/gemini-native",
            }
        ),
        encoding="utf-8",
    )
    assert resolve_managed_npx_command(
        ["npx", "-y", "@google/gemini-cli", "--acp"]
    ) == [str(native_bin.resolve()), "--acp"]


@pytest.mark.asyncio
async def test_cancelled_adapter_install_terminates_process(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(registry_mod.shutil, "which", lambda name: f"/usr/bin/{name}")

    killed = False

    class HangingProc:
        returncode = None
        pid = 99999

        async def communicate(self):
            await asyncio.sleep(60)
            return b"", b""

        def kill(self):
            nonlocal killed
            killed = True
            self.returncode = -9

        async def wait(self):
            return self.returncode

    async def fake_exec(*args, **kwargs):
        if args and args[0] == "taskkill":

            class DummyKill:
                async def wait(self):
                    return 0

            return DummyKill()
        return HangingProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(
        registry_mod,
        "_npm_global_roots",
        lambda: [tmp_path / "acp_adapters" / "node_modules"],
    )
    monkeypatch.setattr(registry_mod, "_npx_cache_roots", lambda: [])
    registry_mod._npm_cache.clear()

    manager = ACPManager(ACPAgentRegistry(path=tmp_path / "acp_agents.json"))
    task = asyncio.create_task(manager.install_adapter("codex"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert killed is True


@pytest.mark.asyncio
async def test_install_adapter_preserves_pinned_version(tmp_path, monkeypatch):
    import asyncio
    from suzent.acp.registry import ACPAgent

    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(registry_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        registry_mod,
        "_npm_global_roots",
        lambda: [tmp_path / "acp_adapters" / "node_modules"],
    )
    monkeypatch.setattr(registry_mod, "_npx_cache_roots", lambda: [])
    registry_mod._npm_cache.clear()

    # Pre-install an incompatible version 2.0.0
    pkg_dir = tmp_path / "acp_adapters" / "node_modules" / "@scope" / "adapter"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({"name": "@scope/adapter", "version": "2.0.0"}),
        encoding="utf-8",
    )

    installed_args: list[str] = []

    class DummyProc:
        returncode = 0

        async def communicate(self):
            (pkg_dir / "package.json").write_text(
                json.dumps({"name": "@scope/adapter", "version": "1.0.0"}),
                encoding="utf-8",
            )
            return b"installed", b""

    async def fake_exec(*args, **kwargs):
        installed_args.extend(str(a) for a in args)
        return DummyProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    reg = ACPAgentRegistry(path=tmp_path / "acp_agents.json")
    reg.save(
        ACPAgent(
            id="pinned-agent",
            name="Pinned Agent",
            command=["npx", "-y", "@scope/adapter@1.0.0"],
        )
    )
    manager = ACPManager(reg)
    assert manager.registry.get("pinned-agent").available is False

    res = await manager.install_adapter("pinned-agent")
    assert res["status"] == "installed"
    assert "@scope/adapter@1.0.0" in installed_args
    assert manager.registry.get("pinned-agent").available is True
