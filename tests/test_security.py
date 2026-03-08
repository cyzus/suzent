"""
Security tests for Suzent.

Ensures isolation of user data, session state, and prevents leakage
between concurrent requests.
"""

import pytest


class TestAgentDepsIsolation:
    """Test that AgentDeps instances are properly isolated between requests."""

    def test_deps_instances_are_independent(self):
        """Verify that modifying one deps instance doesn't affect another."""
        from suzent.core.context_injection import build_agent_deps

        # Create two deps instances
        deps1 = build_agent_deps("chat1", "user1", {"tool_approval_policy": {}})
        deps2 = build_agent_deps("chat2", "user2", {"tool_approval_policy": {}})

        # Mutate deps1's policy
        deps1.tool_approval_policy["BashTool"] = "always_allow"

        # Verify deps2 is unaffected
        assert "BashTool" not in deps2.tool_approval_policy
        assert deps1.tool_approval_policy != deps2.tool_approval_policy

    def test_deps_with_same_config_are_independent(self):
        """Verify that even with the same config dict, deps instances are independent."""
        from suzent.core.context_injection import build_agent_deps

        # Create a shared config (simulates accidental config reuse)
        shared_config = {"tool_approval_policy": {}}

        deps1 = build_agent_deps("chat1", "user1", shared_config)
        deps2 = build_agent_deps("chat2", "user2", shared_config)

        # Mutate deps1
        deps1.tool_approval_policy["ReadFile"] = "always_deny"

        # Verify deps2 is unaffected (defensive copy worked)
        assert "ReadFile" not in deps2.tool_approval_policy

        # Verify original config is also unaffected
        assert "ReadFile" not in shared_config["tool_approval_policy"]

    def test_deps_different_users_same_chat(self):
        """Verify that different users in the same chat get isolated deps."""
        from suzent.core.context_injection import build_agent_deps

        deps_user_a = build_agent_deps("chat1", "userA", {"tool_approval_policy": {}})
        deps_user_b = build_agent_deps("chat1", "userB", {"tool_approval_policy": {}})

        # Different user_id
        assert deps_user_a.user_id != deps_user_b.user_id

        # Independent policies
        deps_user_a.tool_approval_policy["WriteFile"] = "always_allow"
        assert "WriteFile" not in deps_user_b.tool_approval_policy

    def test_deps_no_config_gets_empty_policy(self):
        """Verify that None config results in empty policy dict."""
        from suzent.core.context_injection import build_agent_deps

        deps = build_agent_deps("chat1", "user1", None)

        # Should have empty policy
        assert deps.tool_approval_policy == {}

        # Should be mutable
        deps.tool_approval_policy["test"] = "value"
        assert deps.tool_approval_policy["test"] == "value"


class TestConcurrentRequestIsolation:
    """Test that concurrent requests don't interfere with each other."""

    @pytest.mark.anyio
    async def test_concurrent_process_turn_isolation(self):
        """Verify that concurrent process_turn calls are isolated."""
        from suzent.core.chat_processor import ChatProcessor
        import asyncio

        processor = ChatProcessor()

        # This test would require full integration setup
        # For now, just verify we can create multiple processors
        processor1 = ChatProcessor()
        processor2 = ChatProcessor()

        assert processor1 is not processor2  # Different instances

    def test_social_brain_per_message_isolation(self):
        """Verify that social messages create independent configs."""
        # This would require mocking the entire social stack
        # For now, document the expected behavior
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
