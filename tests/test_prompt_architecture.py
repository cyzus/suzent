from types import SimpleNamespace

from suzent.prompts import STATIC_INSTRUCTIONS, register_dynamic_instructions


class _FakeAgent:
    def __init__(self) -> None:
        self.functions = []

    def instructions(self, fn):
        self.functions.append(fn)
        return fn


def test_static_instructions_do_not_embed_date_context():
    assert "Today's date:" not in STATIC_INSTRUCTIONS


def test_register_dynamic_instructions_registers_all_sections():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )

    assert len(agent.functions) == 7


def test_register_dynamic_instructions_environment_uses_host_paths():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )

    funcs = {fn.__name__: fn for fn in agent.functions}
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            sandbox_enabled=False,
            workspace_root="D:/workspace/suzent",
            custom_volumes=[],
            skill_manager=None,
            social_context={},
        )
    )

    result = funcs["inject_environment_context"](ctx)

    assert "# Environment: Host" in result
    assert "Do NOT use virtual `/mnt/...` paths." in result


def test_register_dynamic_instructions_empty_social_returns_empty_string():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )

    funcs = {fn.__name__: fn for fn in agent.functions}
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            sandbox_enabled=False,
            workspace_root="D:/workspace/suzent",
            custom_volumes=[],
            skill_manager=None,
            social_context={},
        )
    )

    assert funcs["inject_social_context"](ctx) == ""
