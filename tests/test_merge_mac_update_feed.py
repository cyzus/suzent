import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts/merge_mac_update_feed.py"
_spec = importlib.util.spec_from_file_location("merge_mac_update_feed", _SCRIPT)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
merge = _module.merge


def _feed(arch: str, version: str = "1.2.0") -> dict:
    url = f"Suzent-{version}-mac-{arch}.zip"
    return {
        "version": version,
        "files": [{"url": url, "sha512": f"sha-{arch}", "size": 1}],
        "path": url,
        "sha512": f"sha-{arch}",
        "releaseDate": f"2026-11-25T0{1 if arch == 'x64' else 2}:00:00.000Z",
    }


def test_merge_lists_both_arches_with_apple_silicon_first():
    merged = merge([_feed("x64"), _feed("arm64")])
    assert [f["url"] for f in merged["files"]] == [
        "Suzent-1.2.0-mac-arm64.zip",
        "Suzent-1.2.0-mac-x64.zip",
    ]
    assert merged["path"] == "Suzent-1.2.0-mac-arm64.zip"
    assert merged["sha512"] == "sha-arm64"
    assert merged["releaseDate"] == "2026-11-25T02:00:00.000Z"


def test_merge_refuses_mixed_versions():
    with pytest.raises(SystemExit):
        merge([_feed("x64", "1.2.0"), _feed("arm64", "1.2.1")])
