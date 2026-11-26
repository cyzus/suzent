import compileall
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_desktop_runtime", ROOT / "scripts" / "build_desktop_runtime.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_pure_packages_move_into_one_importable_zip(tmp_path: Path) -> None:
    builder = _builder()
    site = tmp_path / "site-packages"
    _write(site / "purepkg" / "__init__.py", "VALUE = 1\n")
    # A namespace subpackage: no __init__.py, found only via a directory entry.
    _write(site / "purepkg" / "inner" / "mod.py", "def answer():\n    return 42\n")
    _write(site / "datapkg" / "__init__.py")
    _write(site / "datapkg" / "table.json", "{}")
    _write(site / "suzent" / "__init__.py")
    compileall.compile_dir(site, quiet=1)

    builder.pack_pure_packages(site)

    assert not (site / "purepkg").exists()
    assert (site / "datapkg" / "table.json").is_file()
    assert (site / "suzent").is_dir()
    probe = (
        "import sys; sys.path.append(sys.argv[1]); "
        "import purepkg, purepkg.inner.mod as m; "
        "assert 'pure-packages.zip' in purepkg.__file__; print(m.answer())"
    )
    zip_path = site / builder.PACKED_ZIP
    out = subprocess.run(
        [sys.executable, "-c", probe, str(zip_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "42"
    assert (site / "pure-packages.pth").read_text().strip() == builder.PACKED_ZIP
