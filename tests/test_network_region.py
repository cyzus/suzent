import gzip
import io
import json
import tarfile

import pytest

from suzent import network_region


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(network_region, "_state_dir", lambda: tmp_path)
    monkeypatch.delenv("SUZENT_CHINA_MIRROR", raising=False)
    monkeypatch.delenv("SUZENT_RELEASE_BASE_URL", raising=False)
    return tmp_path


def test_global_by_default(state):
    assert network_region.china_mode() is False
    assert network_region.release_asset_urls("SHA256SUMS", "v1.2.3") == [
        "https://github.com/cyzus/suzent/releases/download/v1.2.3/SHA256SUMS"
    ]


def test_recorded_region_enables_mirrors_first(state):
    (state / "network-region").write_text("china\n", encoding="utf-8")
    assert network_region.china_mode() is True
    assert network_region.release_asset_urls("suzent.exe", "v1.2.3") == [
        "https://registry.npmmirror.com/-/binary/suzent/v1.2.3/suzent.exe",
        "https://github.com/cyzus/suzent/releases/download/v1.2.3/suzent.exe",
    ]


def test_saved_choice_beats_detection_and_env_beats_both(state, monkeypatch):
    (state / "network-region").write_text("china\n", encoding="utf-8")
    (state / "china-mirror").write_text("off\n", encoding="utf-8")
    assert network_region.china_mode() is False
    monkeypatch.setenv("SUZENT_CHINA_MIRROR", "1")
    assert network_region.china_mode() is True


def test_mirror_env_keeps_values_already_set(state):
    (state / "network-region").write_text("china\n", encoding="utf-8")
    env = network_region.mirror_env({"UV_DEFAULT_INDEX": "https://pypi.example/simple"})
    assert env["UV_DEFAULT_INDEX"] == "https://pypi.example/simple"
    assert env["PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST"].endswith("/chrome-for-testing")


def test_mirror_env_is_untouched_outside_china(state):
    assert network_region.mirror_env({"PATH": "/bin"}) == {"PATH": "/bin"}


def test_latest_tag_in_listing_picks_highest_stable_release():
    listing = json.dumps(
        [
            {"name": "v0.9.0/", "type": "dir"},
            {"name": "v0.17.0/", "type": "dir"},
            {"name": "mobile-v0.2.0/", "type": "dir"},
            {"name": "v0.16.3/", "type": "dir"},
        ]
    )
    assert network_region.latest_tag_in_listing(listing) == "v0.17.0"
    assert network_region.latest_tag_in_listing("[]") == ""
    assert network_region.latest_tag_in_listing("<html>") == ""


def test_latest_release_falls_back_when_the_api_is_rate_limited(state, monkeypatch):
    def rate_limited(timeout):
        raise OSError("HTTP Error 403: rate limit exceeded")

    monkeypatch.setattr(network_region, "_latest_from_api", rate_limited)
    monkeypatch.setattr(
        network_region, "_latest_from_redirect", lambda timeout: "v1.2.3"
    )
    assert network_region.fetch_latest_release()["tag_name"] == "v1.2.3"


def test_china_mode_asks_the_mirror_first(state, monkeypatch):
    (state / "network-region").write_text("china\n", encoding="utf-8")
    calls = []

    def source(name, tag):
        def fetch(timeout):
            calls.append(name)
            return tag

        return fetch

    def npm_unpublished(timeout):
        calls.append("npm")
        raise ValueError("npm mirror has no stable release")

    monkeypatch.setattr(network_region, "_latest_from_npm", npm_unpublished)
    monkeypatch.setattr(
        network_region, "_latest_from_mirror", source("mirror", "v1.2.2")
    )
    monkeypatch.setattr(network_region, "_latest_from_api", source("api", "v1.2.3"))
    assert network_region.fetch_latest_release()["tag_name"] == "v1.2.2"
    assert calls == ["npm", "mirror"]


def test_all_sources_failing_raises(state, monkeypatch):
    def fail(timeout):
        raise OSError("offline")

    monkeypatch.setattr(network_region, "_latest_from_api", fail)
    monkeypatch.setattr(network_region, "_latest_from_redirect", fail)
    with pytest.raises(OSError, match="offline"):
        network_region.fetch_latest_release()


def test_linux_arm64_keeps_playwrights_own_chromium_host(state, monkeypatch):
    (state / "network-region").write_text("china\n", encoding="utf-8")
    monkeypatch.setattr(network_region.sys, "platform", "linux")
    monkeypatch.setattr(network_region.platform, "machine", lambda: "aarch64")
    env = network_region.mirror_env({})
    assert "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST" not in env
    assert env["PLAYWRIGHT_DOWNLOAD_HOST"].endswith("/mirrors/playwright")


def test_repo_sources_add_gitee_only_in_china(state):
    assert network_region.repo_sources() == []
    (state / "network-region").write_text("china\n", encoding="utf-8")
    assert network_region.repo_sources()[0].startswith("https://gitee.com/")


def _npm_tarball(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, contents in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(contents)
            archive.addfile(info, io.BytesIO(contents))
    return gzip.compress(buffer.getvalue())


def test_npm_packages_follow_the_release_file_platform():
    assert network_region.npm_platform_for("suzent-windows-x86_64.exe") == "win32-x64"
    assert (
        network_region.npm_platform_for("suzent-installer-macos-aarch64.dmg")
        == "darwin-arm64"
    )
    assert network_region.npm_platform_for("suzent-linux-x86_64") == "linux-x64"
    assert network_region.npm_tarball_url("darwin-x64", "v1.2.3") == (
        "https://registry.npmmirror.com/@suzent/desktop-darwin-x64/-/"
        "desktop-darwin-x64-1.2.3.tgz"
    )


def test_npm_dist_tags_skip_the_placeholder():
    assert network_region.tag_from_npm_dist_tags('{"latest": "1.2.3"}') == "v1.2.3"
    assert network_region.tag_from_npm_dist_tags('{"latest": "0.0.0"}') == ""
    assert network_region.tag_from_npm_dist_tags('{"latest": "1.2.3-rc.1"}') == ""
    assert network_region.tag_from_npm_dist_tags("[]") == ""


def test_unpack_npm_package_keeps_only_top_level_files(tmp_path):
    tarball = _npm_tarball(
        {
            "package/SHA256SUMS": b"sums",
            "package/nested/file": b"skip",
            "package/../escape": b"skip",
            "other/file": b"skip",
        }
    )
    network_region.unpack_npm_package(tarball, tmp_path / "out")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["SHA256SUMS"]
    assert not (tmp_path / "escape").exists()


def test_china_release_urls_serve_the_npm_package_first(state, monkeypatch):
    (state / "network-region").write_text("china\n", encoding="utf-8")
    tarball = _npm_tarball(
        {"package/SHA256SUMS": b"sums", "package/suzent-linux-x86_64": b"app"}
    )
    requested = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        requested.append(request.full_url)
        return Response(tarball)

    monkeypatch.setattr(network_region, "_npm_packages", {})
    monkeypatch.setattr(network_region.urllib.request, "urlopen", urlopen)
    urls = network_region.release_asset_urls("suzent-linux-x86_64", "v1.2.3")
    assert urls[0].startswith("file://")
    assert urls[1:] == [
        "https://registry.npmmirror.com/-/binary/suzent/v1.2.3/suzent-linux-x86_64",
        "https://github.com/cyzus/suzent/releases/download/v1.2.3/suzent-linux-x86_64",
    ]
    assert requested == [network_region.npm_tarball_url("linux-x64", "v1.2.3")]
    cached = state / "cache" / "npm" / "desktop-linux-x64" / "v1.2.3"
    assert (cached / "suzent-linux-x86_64").read_bytes() == b"app"
    # Unpacked once per process, then read from the cache.
    network_region.release_asset_urls("suzent-installer-linux-x86_64", "v1.2.3")
    assert len(requested) == 1


def test_unavailable_npm_package_falls_through(state, monkeypatch):
    (state / "network-region").write_text("china\n", encoding="utf-8")

    def urlopen(request, timeout):
        raise OSError("404")

    monkeypatch.setattr(network_region, "_npm_packages", {})
    monkeypatch.setattr(network_region.urllib.request, "urlopen", urlopen)
    urls = network_region.release_asset_urls("suzent-linux-x86_64", "v1.2.3")
    assert all(url.startswith("https://") for url in urls)
