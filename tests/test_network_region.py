import json

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

    monkeypatch.setattr(
        network_region, "_latest_from_mirror", source("mirror", "v1.2.2")
    )
    monkeypatch.setattr(network_region, "_latest_from_api", source("api", "v1.2.3"))
    assert network_region.fetch_latest_release()["tag_name"] == "v1.2.2"
    assert calls == ["mirror"]


def test_all_sources_failing_raises(state, monkeypatch):
    def fail(timeout):
        raise OSError("offline")

    monkeypatch.setattr(network_region, "_latest_from_api", fail)
    monkeypatch.setattr(network_region, "_latest_from_redirect", fail)
    with pytest.raises(OSError, match="offline"):
        network_region.fetch_latest_release()
