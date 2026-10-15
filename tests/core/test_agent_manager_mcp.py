from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import PrefixedToolset, SetMetadataToolset

from suzent.agent_manager import _build_mcp_servers


def test_builds_prefixed_v2_mcp_toolsets() -> None:
    config = {
        "mcp_urls": {"remote": "https://example.com/mcp"},
        "mcp_stdio_params": {
            "local": {
                "command": "python",
                "args": ["-m", "example_server"],
                "env": {"EXAMPLE": "1"},
            }
        },
        "mcp_enabled": {"remote": True, "local": True},
        "mcp_headers": {"remote": {"Authorization": "Bearer test"}},
    }

    toolsets = _build_mcp_servers(config)

    assert len(toolsets) == 2
    assert all(isinstance(toolset, SetMetadataToolset) for toolset in toolsets)
    prefixed = [toolset.wrapped for toolset in toolsets]
    assert all(isinstance(toolset, PrefixedToolset) for toolset in prefixed)
    assert [toolset.prefix for toolset in prefixed] == ["remote", "local"]
    assert all(isinstance(toolset.wrapped, MCPToolset) for toolset in prefixed)
    assert [toolset.wrapped.id for toolset in prefixed] == ["remote", "local"]
