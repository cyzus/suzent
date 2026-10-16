"""Exercise signing failure gates without accessing the macOS keychain."""

import os
import subprocess
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
    for name in ("security", "codesign", "ditto", "xcrun", "spctl"):
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
    assert ("spctl --assess" in calls) == (status == "Accepted")
    assert "codesign --force --timestamp --options runtime" in calls
    assert "security delete-keychain" in calls
    assert not list(tmp_path.glob("suzent-macos-signing.*"))
