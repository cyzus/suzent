import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SETUP_PS1 = Path(__file__).resolve().parents[1] / "scripts" / "setup.ps1"


def test_setup_ps1_is_ascii():
    # Windows PowerShell 5.1's `irm | iex` decodes a response without a charset
    # (jsDelivr, many mirrors) as Latin-1, so any non-ASCII byte turns to garbage.
    text = SETUP_PS1.read_bytes()
    bad = [i for i, byte in enumerate(text) if byte > 0x7F]
    assert not bad, f"non-ASCII byte at offset {bad[0]}"


SETUP_SH = SETUP_PS1.with_name("setup.sh")

FAKE_APPIMAGE = """#!/bin/sh
[ "$1" = "--appimage-extract" ] || exit 3
mkdir -p squashfs-root/resources/bin
printf '#!/bin/sh\\necho "bundled suzent $*"\\n' > squashfs-root/resources/bin/suzent
chmod +x squashfs-root/resources/bin/suzent
printf '#!/bin/sh\\n' > squashfs-root/suzent-desktop
chmod +x squashfs-root/suzent-desktop
"""


def _release(directory: Path, files: dict[str, str]) -> str:
    directory.mkdir()
    sums = []
    for name, content in files.items():
        path = directory / name
        path.write_text(content)
        path.chmod(0o755)
        sums.append(f"{hashlib.sha256(content.encode()).hexdigest()}  {name}")
    (directory / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    return directory.as_uri()


def _run_setup(home: Path, base: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "SHELL": "/bin/bash",
        "SUZENT_CHINA_MIRROR": "0",
        "SUZENT_RELEASE_TAG": "v9.9.9",
        "SUZENT_RELEASE_BASE_URL": base,
        "SUZENT_HEADLESS": "1",
        "SUZENT_DIR": str(home / "suzent"),
    }
    return subprocess.run(
        ["bash", str(SETUP_SH), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


linux_only = pytest.mark.skipif(
    sys.platform != "linux"
    or platform.machine() != "x86_64"
    or not shutil.which("curl"),
    reason="exercises the Linux x86_64 install route",
)


@linux_only
def test_setup_sh_installs_portable_app_on_headless_linux(tmp_path: Path):
    base = _release(
        tmp_path / "release", {"Suzent-9.9.9-x86_64.AppImage": FAKE_APPIMAGE}
    )
    home = tmp_path / "home"
    home.mkdir()

    result = _run_setup(home, base)

    assert result.returncode == 0, result.stdout + result.stderr
    shim = home / ".local" / "bin" / "suzent"
    assert "# managed-by: suzent-desktop" in shim.read_text()
    run = subprocess.run(
        [str(shim), "serve"], capture_output=True, text=True, check=True
    )
    assert run.stdout.strip() == "bundled suzent serve"
    assert not (home / "suzent").exists()


@linux_only
def test_setup_sh_keeps_a_command_it_does_not_own(tmp_path: Path):
    base = _release(
        tmp_path / "release", {"Suzent-9.9.9-x86_64.AppImage": FAKE_APPIMAGE}
    )
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    foreign = home / ".local" / "bin" / "suzent"
    foreign.write_text("#!/bin/sh\necho mine\n")

    result = _run_setup(home, base)

    assert result.returncode == 0, result.stdout + result.stderr
    assert foreign.read_text() == "#!/bin/sh\necho mine\n"


@linux_only
def test_setup_sh_package_mode_fails_without_an_installer(tmp_path: Path):
    base = _release(tmp_path / "release", {"suzent-linux-x86_64": "ui"})
    home = tmp_path / "home"
    home.mkdir()

    result = _run_setup(home, base, "--package")

    assert result.returncode == 1
    assert "has no installer this machine can use" in result.stdout
