"""Every module ``src/suzent`` imports must be installed.

Lazy imports (inside functions, often wrapped in ``try/except ImportError``)
fail quietly at runtime, so dropping a dependency that only arrived
transitively goes unnoticed: trimming ``markitdown[all]`` removed ``pydub``,
which ``SpeechOutput`` needs to decode compressed TTS audio. CI installs all
extras, so any module named here that cannot be found is a missing
declaration in ``pyproject.toml``.
"""

import ast
import importlib.util
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "suzent"

# Platform-only modules, or optional integrations that are never a declared
# dependency (users install them themselves).
_IGNORED = {
    # Windows / POSIX only
    "winreg",
    "msvcrt",
    "winsound",
    "_winapi",
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "pywintypes",
    "fcntl",
    "termios",
    "tty",
    "pwd",
    "grp",
    "resource",
    # Known gap, predates this test: the voice pipeline's VAD has never been a
    # declared dependency, so the pipeline logs "webrtcvad not installed" and
    # stays off. Remove this entry when it is declared (or the import goes).
    "webrtcvad",
}


def _imported_top_level_modules() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                found.setdefault(name.split(".")[0], str(path.relative_to(SRC)))
    return found


def test_every_imported_module_is_installed():
    stdlib = set(sys.stdlib_module_names)
    missing = {
        module: where
        for module, where in _imported_top_level_modules().items()
        if module not in stdlib
        and module not in _IGNORED
        and module != "suzent"
        and importlib.util.find_spec(module) is None
    }
    assert not missing, (
        "Imported but not installed (declare them in pyproject.toml): "
        + ", ".join(f"{m} ({w})" for m, w in sorted(missing.items()))
    )
