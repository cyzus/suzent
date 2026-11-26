import sys
import zipfile
import zipimport
from pathlib import Path

import pytest

from suzent.import_caches import refresh_import_caches


def test_a_package_installed_later_becomes_importable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "plugin-deps"
    monkeypatch.syspath_prepend(str(target))
    with pytest.raises(ImportError):
        __import__("late_pkg_for_cache_test")
    (target / "late_pkg_for_cache_test").mkdir(parents=True)
    (target / "late_pkg_for_cache_test" / "__init__.py").write_text("X = 1\n")

    refresh_import_caches()

    module = __import__("late_pkg_for_cache_test")
    assert module.X == 1
    sys.modules.pop("late_pkg_for_cache_test", None)


def test_zip_directories_are_not_reread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "pure-packages.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("zipped_mod_for_cache_test.py", "Y = 2\n")
    monkeypatch.syspath_prepend(str(archive))
    __import__("zipped_mod_for_cache_test")
    finder = sys.path_importer_cache[str(archive)]
    assert isinstance(finder, zipimport.zipimporter)
    calls: list[str] = []
    monkeypatch.setattr(
        zipimport.zipimporter, "invalidate_caches", lambda self: calls.append("zip")
    )

    refresh_import_caches()

    assert calls == []
    sys.modules.pop("zipped_mod_for_cache_test", None)
