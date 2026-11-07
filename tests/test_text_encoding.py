"""Guard against text I/O that relies on the platform's default encoding.

On Windows with a Chinese locale the default is gbk, so reading a UTF-8 file
without ``encoding="utf-8"`` fails as soon as it holds a non-ASCII byte.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRS = ("src", "scripts")
BINARY_OPENERS = {
    "os",
    "wave",
    "tarfile",
    "zipfile",
    "gzip",
    "Image",
    "webbrowser",
    "opener",
}


def _mode(call: ast.Call, position: int) -> str | None:
    if len(call.args) > position:
        arg = call.args[position]
        return arg.value if isinstance(arg, ast.Constant) else None
    for keyword in call.keywords:
        if keyword.arg == "mode":
            value = keyword.value
            return value.value if isinstance(value, ast.Constant) else None
    return "r"


def _is_text_mode(mode: str | None) -> bool:
    return mode is None or "b" not in mode


def _missing_encoding(call: ast.Call) -> bool:
    if any(keyword.arg == "encoding" for keyword in call.keywords):
        return False
    match call.func:
        case ast.Name(id="open"):
            return _is_text_mode(_mode(call, 1))
        case ast.Attribute(attr="read_text"):
            return not call.args
        case ast.Attribute(attr="write_text"):
            return len(call.args) < 2
        case ast.Attribute(attr="open", value=ast.Name(id=name)) if (
            name in BINARY_OPENERS
        ):
            return False
        case ast.Attribute(attr="open"):
            return _is_text_mode(_mode(call, 0))
    return False


def _python_files() -> list[Path]:
    return sorted(
        path for folder in SCANNED_DIRS for path in (REPO_ROOT / folder).rglob("*.py")
    )


@pytest.mark.parametrize(
    "path", _python_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_text_io_names_an_encoding(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _missing_encoding(node)
    ]
    assert not offenders, f'Pass encoding="utf-8" at: {", ".join(offenders)}'
