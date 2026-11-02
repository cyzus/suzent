"""A half-removed *.dist-info must not break plugin package checks.

On Windows an upgrade can leave e.g. ``lxml-5.4.0.dist-info/licenses/`` with
no METADATA (the running backend held files open), which made /plugins
return 500 and the settings page show "Failed to fetch".
"""

import pytest

from suzent.plugins import deps


class _Dist:
    def __init__(self, metadata):
        self._metadata = metadata

    @property
    def metadata(self):
        if isinstance(self._metadata, Exception):
            raise self._metadata
        return self._metadata


@pytest.mark.parametrize(
    "broken",
    [None, FileNotFoundError("METADATA"), {"Name": None}],
    ids=["metadata-none", "metadata-raises", "name-missing"],
)
def test_broken_distributions_are_skipped(monkeypatch, broken):
    dists = [_Dist(broken), _Dist({"Name": "python-telegram-bot"})]
    monkeypatch.setattr(deps.importlib.metadata, "distributions", lambda **_: dists)

    assert deps._installed("python_telegram_bot")
    assert not deps._installed("slack-sdk")


def test_real_half_removed_dist_info_on_disk(tmp_path):
    """The exact leftover seen in the field: only a licenses/ folder."""
    leftover = tmp_path / "lxml-5.4.0.dist-info" / "licenses"
    leftover.mkdir(parents=True)
    good = tmp_path / "zstandard-0.25.0.dist-info"
    good.mkdir()
    (good / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: zstandard\nVersion: 0.25.0\n", "utf-8"
    )

    assert deps._installed("zstandard", [str(tmp_path)])
    assert not deps._installed("lxml", [str(tmp_path)])
