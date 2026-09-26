import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/mobile_release.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("mobile_release", SCRIPT)
assert spec is not None and spec.loader is not None
mobile_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile_release)
sys.path.pop(0)
release_metadata = mobile_release.release_metadata


@pytest.fixture
def release_root(tmp_path: Path) -> Path:
    folder = tmp_path / "packages/mobile-contract"
    folder.mkdir(parents=True)
    (folder / "version.json").write_text(json.dumps({"version": "0.2.0", "build": 8}))
    (folder / "CHANGELOG.md").write_text(
        "# Mobile\n\n## [mobile-v0.2.0] - 2026-09-26\n\nNew release.\n\n"
        "## [mobile-v0.1.0]\n\nOlder notes.\n"
    )
    return tmp_path


def test_exact_release_notes_and_stable_build(release_root: Path) -> None:
    result = release_metadata(release_root, "mobile-v0.2.0")
    assert result == {"version": "0.2.0", "build": 100008, "notes": "New release.\n"}
    assert release_metadata(release_root, "mobile-v0.2.0") == result


@pytest.mark.parametrize(
    "tag", ["v0.2.0", "main", "mobile-v0.1.0", "mobile-v01.2.0", "mobile-v0.2.0\n"]
)
def test_reject_wrong_or_invalid_tag(release_root: Path, tag: str) -> None:
    with pytest.raises(ValueError):
        release_metadata(release_root, tag)


def test_require_product_changelog(release_root: Path) -> None:
    (release_root / "packages/mobile-contract/CHANGELOG.md").write_text("# Empty\n")
    with pytest.raises(ValueError, match="changelog"):
        release_metadata(release_root, "mobile-v0.2.0")


@pytest.mark.parametrize("build", [True, 0, -1, "1", 2_100_000_000])
def test_reject_invalid_or_overflowing_build(release_root: Path, build: object) -> None:
    (release_root / "packages/mobile-contract/version.json").write_text(
        json.dumps({"version": "0.2.0", "build": build})
    )
    with pytest.raises(ValueError):
        release_metadata(release_root, "mobile-v0.2.0")


def test_cli_rejects_tag_outside_main(
    release_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=release_root, text=True
        ).strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Release Test")
    git("add", ".")
    git("commit", "-m", "base")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("switch", "-c", "unreviewed")
    (release_root / "unreviewed.txt").write_text("not on main")
    git("add", ".")
    git("commit", "-m", "unreviewed")
    git("tag", "mobile-v0.2.0")
    monkeypatch.setattr(mobile_release, "ROOT", release_root)
    monkeypatch.setattr(
        sys,
        "argv",
        ["mobile_release.py", "mobile-v0.2.0", "--output", str(release_root / "out")],
    )
    with pytest.raises(subprocess.CalledProcessError):
        mobile_release.main()
    assert not (release_root / "out").exists()
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    mobile_release.main()
    assert (
        json.loads((release_root / "out/metadata.json").read_text())["build"] == 100008
    )
    assert (release_root / "out/notes.md").read_text() == "New release.\n"
    git("checkout", "main")
    with pytest.raises(SystemExit, match="exact release tag"):
        mobile_release.main()
