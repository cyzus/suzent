import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_mobile_version.py"
spec = importlib.util.spec_from_file_location("mobile_version", SCRIPT)
assert spec is not None and spec.loader is not None
mobile_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile_version)


@pytest.fixture
def version_root(tmp_path: Path) -> Path:
    source = tmp_path / "packages/mobile-contract/version.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"version": "0.2.3", "build": 7}))
    (tmp_path / "apps/ios/Config").mkdir(parents=True)
    (tmp_path / "apps/android").mkdir(parents=True)
    return tmp_path


def test_ci_build_override_preserves_product_version_and_source(
    version_root: Path,
) -> None:
    outputs = mobile_version.version_outputs(version_root, 1042)
    assert (
        "MARKETING_VERSION = 0.2.3\nCURRENT_PROJECT_VERSION = 1042"
        in outputs[version_root / "apps/ios/Config/Version.xcconfig"]
    )
    assert (
        "versionName=0.2.3\nversionCode=1042"
        in outputs[version_root / "apps/android/version.properties"]
    )
    assert json.loads(
        (version_root / "packages/mobile-contract/version.json").read_text()
    ) == {"version": "0.2.3", "build": 7}


@pytest.mark.parametrize("build", [0, -1, True, "42", 2_100_000_001])
def test_invalid_build_is_rejected(version_root: Path, build: object) -> None:
    with pytest.raises(ValueError, match="build number"):
        mobile_version.version_outputs(version_root, build)


@pytest.mark.parametrize("version", ["1.0", "01.2.3", "1.2.3\ninjected=true", 123])
def test_invalid_version_is_rejected(version_root: Path, version: object) -> None:
    (version_root / "packages/mobile-contract/version.json").write_text(
        json.dumps({"version": version, "build": 1})
    )
    with pytest.raises(ValueError, match="major.minor.patch"):
        mobile_version.version_outputs(version_root)


def test_check_detects_drift_and_generation_repairs_it(
    version_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mobile_version, "ROOT", version_root)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    mobile_version.main()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check"])
    mobile_version.main()
    (version_root / "apps/android/version.properties").write_text("versionCode=99\n")
    with pytest.raises(SystemExit, match="Stale mobile version"):
        mobile_version.main()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    mobile_version.main()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check"])
    mobile_version.main()
