"""
Unit tests for the Node Manager.
"""

import pytest

from suzent.nodes.base import NodeBase, NodeCapability
from suzent.nodes.manager import NodeManager


class MockNode(NodeBase):
    """A simple mock node for testing."""

    def __init__(
        self,
        node_id="test-node-1",
        display_name="TestNode",
        platform="desktop",
        capabilities=None,
    ):
        super().__init__(node_id, display_name, platform, capabilities)
        self._invoke_result = {"success": True, "result": "mock_result"}

    async def invoke(self, command, params=None):
        return self._invoke_result

    async def heartbeat(self):
        return True


class TestNodeCapability:
    def test_create_capability(self):
        cap = NodeCapability(name="camera.snap", description="Take a photo")
        assert cap.name == "camera.snap"
        assert cap.description == "Take a photo"
        assert cap.params_schema == {}

    def test_create_capability_with_schema(self):
        cap = NodeCapability(
            name="system.run",
            description="Run a command",
            params_schema={"command": "str", "timeout": "int"},
        )
        assert cap.params_schema == {"command": "str", "timeout": "int"}


class TestNodeBase:
    def test_node_has_capability(self):
        caps = [
            NodeCapability(name="camera.snap"),
            NodeCapability(name="system.notify"),
        ]
        node = MockNode(capabilities=caps)
        assert node.has_capability("camera.snap")
        assert node.has_capability("system.notify")
        assert not node.has_capability("clipboard.paste")

    def test_node_get_capability(self):
        caps = [NodeCapability(name="camera.snap", description="Take photo")]
        node = MockNode(capabilities=caps)
        cap = node.get_capability("camera.snap")
        assert cap is not None
        assert cap.description == "Take photo"
        assert node.get_capability("nonexistent") is None

    def test_node_to_dict(self):
        caps = [NodeCapability(name="echo.test", description="Echo back")]
        node = MockNode(display_name="Phone", platform="ios", capabilities=caps)
        d = node.to_dict()
        assert d["display_name"] == "Phone"
        assert d["platform"] == "ios"
        assert d["status"] == "connected"
        assert len(d["capabilities"]) == 1
        assert d["capabilities"][0]["name"] == "echo.test"


class TestNodeManager:
    def setup_method(self):
        self.manager = NodeManager()

    def test_register_and_list(self):
        node = MockNode()
        self.manager.register_node(node)

        nodes = self.manager.list_nodes()
        assert len(nodes) == 1
        assert nodes[0]["node_id"] == "test-node-1"

    def test_register_multiple_nodes(self):
        node1 = MockNode(node_id="n1", display_name="Node1")
        node2 = MockNode(node_id="n2", display_name="Node2")
        self.manager.register_node(node1)
        self.manager.register_node(node2)

        assert len(self.manager.list_nodes()) == 2

    def test_unregister(self):
        node = MockNode()
        self.manager.register_node(node)
        assert len(self.manager.list_nodes()) == 1

        result = self.manager.unregister_node("test-node-1")
        assert result is True
        assert len(self.manager.list_nodes()) == 0
        assert node.status == "disconnected"

    def test_unregister_unknown(self):
        result = self.manager.unregister_node("nonexistent")
        assert result is False

    def test_get_by_id(self):
        node = MockNode(node_id="abc123")
        self.manager.register_node(node)

        found = self.manager.get_node("abc123")
        assert found is not None
        assert found.node_id == "abc123"

    def test_get_by_name(self):
        node = MockNode(display_name="MyPhone")
        self.manager.register_node(node)

        found = self.manager.get_node("myphone")  # case-insensitive
        assert found is not None
        assert found.display_name == "MyPhone"

    def test_get_not_found(self):
        assert self.manager.get_node("nothing") is None

    @pytest.mark.asyncio
    async def test_invoke_dispatches(self):
        caps = [NodeCapability(name="echo.test")]
        node = MockNode(capabilities=caps)
        self.manager.register_node(node)

        result = await self.manager.invoke("test-node-1", "echo.test", {"msg": "hi"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_invoke_unknown_node(self):
        with pytest.raises(ValueError, match="Node not found"):
            await self.manager.invoke("nonexistent", "echo.test")

    @pytest.mark.asyncio
    async def test_invoke_unsupported_command(self):
        caps = [NodeCapability(name="echo.test")]
        node = MockNode(capabilities=caps)
        self.manager.register_node(node)

        with pytest.raises(ValueError, match="does not support"):
            await self.manager.invoke("test-node-1", "camera.snap")

    @pytest.mark.asyncio
    async def test_invoke_disconnected_node(self):
        caps = [NodeCapability(name="echo.test")]
        node = MockNode(capabilities=caps)
        node.status = "disconnected"
        self.manager.register_node(node)

        with pytest.raises(ValueError, match="disconnected"):
            await self.manager.invoke("test-node-1", "echo.test")

    def test_describe_node(self):
        caps = [NodeCapability(name="camera.snap", description="Take photo")]
        node = MockNode(display_name="Phone", capabilities=caps)
        self.manager.register_node(node)

        info = self.manager.describe_node("test-node-1")
        assert info is not None
        assert info["display_name"] == "Phone"
        assert len(info["capabilities"]) == 1

    def test_describe_not_found(self):
        assert self.manager.describe_node("nothing") is None

    def test_connected_count(self):
        n1 = MockNode(node_id="n1")
        n2 = MockNode(node_id="n2")
        n2.status = "disconnected"
        self.manager.register_node(n1)
        self.manager.register_node(n2)

        assert self.manager.connected_count == 1
