"""The registry's public surface, including what `import *` reaches.

`suzent.tools.names` is re-exported through the registry for backwards
compatibility. Listing those aliases in `__all__` would quietly shrink a
wildcard import down to them, dropping the registry APIs documented in
`docs/02-concepts/tools/tools.md`.
"""

import pytest

_DOCUMENTED_APIS = (
    "get_tool_function",
    "list_available_tools",
    "get_tool_registry",
    "get_tool_capabilities",
    "list_configurable_tools",
)

_REEXPORTED_FROM_NAMES = (
    "migrate_shell_tool_names",
    "expand_tool_dependencies",
    "SHELL_TOOL_CLASS_NAMES",
    "AGENT_LIFECYCLE_TOOL_NAMES",
    "LEGACY_SHELL_TOOL_NAMES",
)


def _wildcard_namespace() -> dict:
    namespace: dict = {}
    exec("from suzent.tools.registry import *", namespace)  # noqa: S102
    return namespace


@pytest.mark.parametrize("name", _DOCUMENTED_APIS + _REEXPORTED_FROM_NAMES)
def test_wildcard_import_reaches_the_public_registry_surface(name):
    assert name in _wildcard_namespace()


@pytest.mark.parametrize("name", _REEXPORTED_FROM_NAMES)
def test_reexports_are_the_objects_from_the_names_module(name):
    from suzent.tools import names, registry

    assert getattr(registry, name) is getattr(names, name)
