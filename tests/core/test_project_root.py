"""Suzent finds its bundled resources outside a source checkout.

``core/providers/catalog.py`` and ``core/model_registry.py`` used to locate
``config/`` with ``Path(__file__).parents[N]``, which only works in the repo:
installed into site-packages (wheel, MSIX), they looked in ``Lib/config`` and
found zero providers, so onboarding showed "no matching provider".
"""

import ast
import subprocess
import sys
from pathlib import Path

import suzent

SRC = Path(suzent.__file__).resolve().parent
REPO_CONFIG = SRC.parents[1] / "config"


def test_no_module_guesses_the_repo_root_from_its_own_path():
    """Only config/paths.py may derive the root from ``__file__``; everything
    else must use PROJECT_DIR so installed builds and overrides work."""
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.relative_to(SRC).as_posix() == "config/paths.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "parents"
                and "__file__" in ast.unparse(node.value)
            ):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not offenders, offenders


def test_project_dir_override_feeds_the_provider_catalog(tmp_path):
    """With SUZENT_PROJECT_DIR set, providers load from that folder's config/."""
    root = tmp_path / "app"
    (root / "config").mkdir(parents=True)
    for name in ("providers.json", "provider_defaults.json"):
        source = REPO_CONFIG / name
        if source.exists():
            (root / "config" / name).write_bytes(source.read_bytes())

    code = (
        "from suzent.config.paths import PROJECT_DIR\n"
        "from suzent.core.providers import catalog\n"
        "from suzent.core import model_registry\n"
        "print(PROJECT_DIR)\n"
        "print(catalog._CONFIG_DIR)\n"
        "print(model_registry._CAPABILITIES_PATH.parent)\n"
        "print(len(catalog.PROVIDER_REGISTRY))\n"
    )
    env = {
        **__import__("os").environ,
        "SUZENT_PROJECT_DIR": str(root),
        "SUZENT_DATA_DIR": str(tmp_path / "data"),
    }
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    ).stdout.splitlines()

    assert Path(out[0]) == root.resolve()
    assert Path(out[1]) == root.resolve() / "config"
    assert Path(out[2]) == root.resolve() / "config"
    assert int(out[3]) > 0
