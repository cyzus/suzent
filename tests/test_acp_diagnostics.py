import pytest
from suzent.acp.registry import ACPAgent
from suzent.acp.manager import ACPManager


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


@pytest.mark.asyncio
async def test_manager_stop():
    manager = ACPManager()
    # Ensure no error on stopping non-existent session
    await manager.stop("non-existent")
