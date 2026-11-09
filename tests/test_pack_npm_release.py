import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/pack_npm_release.py"
spec = importlib.util.spec_from_file_location("suzent_pack_npm_release", SCRIPT)
pack_npm_release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pack_npm_release
spec.loader.exec_module(pack_npm_release)

MACOS_RELEASE_ASSETS = [
    "suzent-macos-aarch64",
    "suzent-installer-macos-aarch64",
    "suzent-installer-macos-aarch64.dmg",
    "suzent-macos-x86_64",
    "suzent-installer-macos-x86_64",
    "suzent-installer-macos-x86_64.dmg",
    "suzent-installer-macos.dmg",
]


def test_each_mac_package_carries_only_the_universal_disk_image():
    assert pack_npm_release.platform_assets(MACOS_RELEASE_ASSETS, "macos-aarch64") == [
        "suzent-installer-macos-aarch64",
        "suzent-installer-macos.dmg",
        "suzent-macos-aarch64",
    ]
    assert pack_npm_release.platform_assets(MACOS_RELEASE_ASSETS, "macos-x86_64") == [
        "suzent-installer-macos-x86_64",
        "suzent-installer-macos.dmg",
        "suzent-macos-x86_64",
    ]


def test_releases_without_the_universal_image_keep_their_arch_disk_image():
    assets = ["suzent-macos-aarch64", "suzent-installer-macos-aarch64.dmg"]
    assert pack_npm_release.platform_assets(assets, "macos-aarch64") == [
        "suzent-installer-macos-aarch64.dmg",
        "suzent-macos-aarch64",
    ]


def test_other_platforms_ignore_the_universal_mac_image():
    assets = [
        "suzent-installer-macos.dmg",
        "suzent-windows-x86_64.exe",
        "suzent-installer-windows-x86_64.exe",
    ]
    assert pack_npm_release.platform_assets(assets, "windows-x86_64") == [
        "suzent-installer-windows-x86_64.exe",
        "suzent-windows-x86_64.exe",
    ]
