"""Exercise signing failure gates without accessing the macOS keychain."""

import os
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sign-macos-release.sh"
CREDENTIALS = {
    "MACOS_CERTIFICATE_BASE64": "dGVzdA==",
    "MACOS_CERTIFICATE_PASSWORD": "test",
    "MACOS_SIGNING_IDENTITY": "Developer ID Application: Test (TEAM)",
    "APP_STORE_CONNECT_KEY_BASE64": "dGVzdA==",
    "APP_STORE_CONNECT_KEY_ID": "KEYID",
    "APP_STORE_CONNECT_ISSUER_ID": "issuer",
}


def test_missing_credentials_fail_before_keychain_access() -> None:
    env = {key: value for key, value in os.environ.items() if key not in CREDENTIALS}
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "Missing MACOS_CERTIFICATE_BASE64" in result.stdout


@pytest.mark.parametrize("status", ["Accepted", "Invalid", "In Progress"])
def test_notarization_gate_and_cleanup(tmp_path: Path, status: str) -> None:
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "calls.log"
    stub = commands / "stub"
    stub.write_text(
        "#!/bin/bash\n"
        'echo "$(basename "$0") $*" >> "$CALL_LOG"\n'
        'if [[ "$(basename "$0")" == xcrun ]]; then\n'
        '  printf \'{"status":"%s","id":"test-id"}\\n\' "$NOTARY_STATUS"\n'
        "fi\n"
    )
    stub.chmod(0o755)
    for name in ("security", "codesign", "ditto", "xcrun"):
        (commands / name).symlink_to(stub)
    binary = tmp_path / "suzent"
    binary.write_text("test executable")
    env = {
        **os.environ,
        **CREDENTIALS,
        "PATH": f"{commands}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "CALL_LOG": str(log),
        "NOTARY_STATUS": status,
        "MACOS_SIGNED_ARCHIVE": str(tmp_path / "candidate.tar.gz"),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), str(binary)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log.read_text()
    assert (result.returncode == 0) == (status == "Accepted"), result.stderr
    assert ("--check-notarization" in calls) == (status == "Accepted")
    assert "codesign --force --timestamp --options runtime" in calls
    with tarfile.open(tmp_path / "candidate.tar.gz") as archive:
        member = archive.extractfile("./suzent")
        assert member is not None
        assert member.read() == binary.read_bytes()
    assert "security delete-keychain" in calls
    assert not list(tmp_path.glob("suzent-macos-signing.*"))


def _stub_commands(tmp_path: Path) -> tuple[Path, Path]:
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "calls.log"
    stub = commands / "stub"
    stub.write_text(
        "#!/bin/bash\n"
        'echo "$(basename "$0") $*" >> "$CALL_LOG"\n'
        'if [[ "$(basename "$0")" == xcrun && "$1" == notarytool ]]; then\n'
        '  status="$NOTARY_STATUS"\n'
        '  [[ "$3" == *.dmg ]] && status="$DMG_NOTARY_STATUS"\n'
        '  printf \'{"status":"%s","id":"%s"}\\n\' "$status" "$(basename "$3")"\n'
        "fi\n"
        'if [[ "$(basename "$0")" == hdiutil && "$1" == create ]]; then\n'
        '  echo "disk image" > "${@: -1}"\n'
        "fi\n"
    )
    stub.chmod(0o755)
    for name in ("security", "codesign", "ditto", "xcrun", "hdiutil", "spctl"):
        (commands / name).symlink_to(stub)
    return commands, log


def _installer_env(tmp_path: Path, commands: Path, log: Path) -> dict[str, str]:
    app = tmp_path / "Suzent Installer.app"
    (app / "Contents/MacOS").mkdir(parents=True)
    return {
        **os.environ,
        **CREDENTIALS,
        "PATH": f"{commands}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "CALL_LOG": str(log),
        "MACOS_INSTALLER_APP": str(app),
        "MACOS_INSTALLER_BINARY": str(tmp_path / "suzent-installer"),
        "MACOS_INSTALLER_DMG": str(tmp_path / "suzent-installer-macos-aarch64.dmg"),
        "MACOS_SIGNED_ARCHIVE": str(tmp_path / "candidate.tar.gz"),
    }


def test_partial_installer_config_fails_before_keychain_access(tmp_path: Path) -> None:
    commands, log = _stub_commands(tmp_path)
    binary = tmp_path / "suzent-installer"
    binary.write_text("installer")
    env = _installer_env(tmp_path, commands, log)
    del env["MACOS_INSTALLER_DMG"]
    result = subprocess.run(
        ["bash", str(SCRIPT), str(binary)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Missing MACOS_INSTALLER_DMG" in result.stdout
    assert not log.exists()


def test_embedded_installer_must_be_a_signed_executable(tmp_path: Path) -> None:
    commands, log = _stub_commands(tmp_path)
    other = tmp_path / "suzent"
    other.write_text("app")
    env = _installer_env(tmp_path, commands, log)
    result = subprocess.run(
        ["bash", str(SCRIPT), str(other)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "must be one of the executables" in result.stdout
    assert not log.exists()


@pytest.mark.parametrize(
    ("assets_status", "dmg_status"),
    [("Accepted", "Accepted"), ("Accepted", "Invalid"), ("Invalid", "Accepted")],
)
def test_installer_disk_image_is_stapled_only_after_acceptance(
    tmp_path: Path, assets_status: str, dmg_status: str
) -> None:
    commands, log = _stub_commands(tmp_path)
    binary = tmp_path / "suzent-installer"
    binary.write_text("installer")
    env = {
        **_installer_env(tmp_path, commands, log),
        "NOTARY_STATUS": assets_status,
        "DMG_NOTARY_STATUS": dmg_status,
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), str(binary)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log.read_text().splitlines()
    accepted = assets_status == dmg_status == "Accepted"
    assert (result.returncode == 0) == accepted, result.stderr
    submissions = [call for call in calls if call.startswith("xcrun notarytool submit")]
    assert sorted(call.split()[3].rsplit("/", 1)[-1] for call in submissions) == [
        "assets.zip",
        "suzent-installer-macos-aarch64.dmg",
    ]
    stapling = [
        "xcrun stapler staple",
        "xcrun stapler validate",
        "spctl --assess --type open --context context:primary-signature",
        "spctl --assess --type execute",
        "hdiutil detach",
    ]
    for prefix in stapling:
        assert any(call.startswith(prefix) for call in calls) == accepted, prefix
    helper = "Suzent Installer.app/Contents/Helpers/suzent-installer"
    assert any(call.startswith("ditto") and call.endswith(helper) for call in calls)
    assert any(
        call.startswith("codesign --force --timestamp --options runtime")
        and call.endswith("Suzent Installer.app")
        for call in calls
    )
    with tarfile.open(tmp_path / "candidate.tar.gz") as archive:
        assert {"./suzent-installer", "suzent-installer-macos-aarch64.dmg"} <= set(
            archive.getnames()
        )
    assert "security delete-keychain" in "\n".join(calls)
    assert not list(tmp_path.glob("suzent-macos-signing.*"))
