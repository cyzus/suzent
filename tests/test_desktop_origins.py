import re

import pytest

from suzent.server import _allowed_origin_regex


@pytest.mark.parametrize(
    "origin",
    [
        "suzent://app",
        "tauri://localhost",
        "http://tauri.localhost",
        "http://127.0.0.1:18080",
    ],
)
def test_desktop_and_loopback_origins_may_call_the_backend(origin: str) -> None:
    assert re.fullmatch(_allowed_origin_regex(), origin)


@pytest.mark.parametrize(
    "origin", ["suzent://evil", "https://suzent.app", "https://example.com"]
)
def test_other_origins_are_refused(origin: str) -> None:
    assert not re.fullmatch(_allowed_origin_regex(), origin)
