import base64
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/mobile/play_publish.py"
spec = importlib.util.spec_from_file_location("play_publish", SCRIPT)
assert spec is not None and spec.loader is not None
play = importlib.util.module_from_spec(spec)
spec.loader.exec_module(play)
sys.path.remove(str(SCRIPT.parent))

APP = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.suzent.mobile"
NOTES = "### Release notes\n- Fix **long** chats.\n"


class FakePlay:
    def __init__(self, overrides: dict[tuple[str, str], Any] | None = None) -> None:
        self.routes: dict[tuple[str, str], Any] = {
            ("POST", "/edits"): {"id": "e1"},
            ("GET", "/edits/e1/tracks/alpha"): {
                "track": "alpha",
                "releases": [{"status": "completed", "versionCodes": ["100016"]}],
            },
            ("GET", "/edits/e1/bundles"): {"bundles": [{"versionCode": 100016}]},
            ("POST", "/edits/e1/bundles?uploadType=media"): {"versionCode": 100017},
            ("GET", "/edits/e1/listings"): {
                "listings": [{"language": "en-US"}, {"language": "zh-CN"}]
            },
            ("PUT", "/edits/e1/tracks/alpha"): {},
            ("POST", "/edits/e1:commit"): {"id": "e1"},
            ("DELETE", "/edits/e1"): {},
        }
        self.routes.update(overrides or {})
        self.calls: list[tuple[str, str, bytes | None]] = []

    def __call__(self, method: str, url: str, body: bytes | None, _: str) -> Any:
        path = url.split("com.suzent.mobile", 1)[1]
        self.calls.append((method, path, body))
        if (method, path) not in self.routes:
            raise AssertionError(f"Unexpected {method} {path}")
        response = self.routes[(method, path)]
        if isinstance(response, Exception):
            raise response
        return response

    def methods(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p, _ in self.calls]


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    path = tmp_path / "suzent-0.7.2-android.aab"
    path.write_bytes(b"aab-bytes")
    return path


def test_uploads_bundle_and_releases_to_track(bundle: Path) -> None:
    fake = FakePlay()
    assert play.PlayPublisher(fake, "com.suzent.mobile").publish(
        bundle, 100017, "0.7.2", NOTES, "alpha"
    )
    upload = next(b for m, p, b in fake.calls if "uploadType" in p)
    assert upload == b"aab-bytes"
    body = json.loads(next(b for m, p, b in fake.calls if m == "PUT"))
    assert body["releases"] == [
        {
            "name": "0.7.2",
            "versionCodes": ["100017"],
            "status": "completed",
            "releaseNotes": [
                {"language": "en-US", "text": "• Fix long chats."},
                {"language": "zh-CN", "text": "• Fix long chats."},
            ],
        }
    ]
    assert fake.methods()[-1] == ("POST", "/edits/e1:commit")


def test_already_live_version_is_left_alone(bundle: Path) -> None:
    fake = FakePlay(
        {
            ("GET", "/edits/e1/tracks/alpha"): {
                "releases": [{"status": "completed", "versionCodes": ["100017"]}]
            }
        }
    )
    assert not play.PlayPublisher(fake, "com.suzent.mobile").publish(
        bundle, 100017, "0.7.2", NOTES, "alpha"
    )
    assert fake.methods() == [
        ("POST", "/edits"),
        ("GET", "/edits/e1/tracks/alpha"),
        ("DELETE", "/edits/e1"),
    ]


def test_reuses_bundle_uploaded_by_an_earlier_attempt(bundle: Path) -> None:
    fake = FakePlay(
        {("GET", "/edits/e1/bundles"): {"bundles": [{"versionCode": 100017}]}}
    )
    play.PlayPublisher(fake, "com.suzent.mobile").publish(
        bundle, 100017, "0.7.2", NOTES, "alpha"
    )
    assert not any("uploadType" in p for _, p in fake.methods())
    assert fake.methods()[-1] == ("POST", "/edits/e1:commit")


def test_failure_discards_the_edit(bundle: Path) -> None:
    fake = FakePlay({("PUT", "/edits/e1/tracks/alpha"): play.PlayError("boom")})
    with pytest.raises(play.PlayError, match="boom"):
        play.PlayPublisher(fake, "com.suzent.mobile").publish(
            bundle, 100017, "0.7.2", NOTES, "alpha"
        )
    assert fake.methods()[-1] == ("DELETE", "/edits/e1")
    assert ("POST", "/edits/e1:commit") not in fake.methods()


def test_wrong_version_code_is_rejected(bundle: Path) -> None:
    fake = FakePlay(
        {("POST", "/edits/e1/bundles?uploadType=media"): {"versionCode": 99}}
    )
    with pytest.raises(play.PlayError, match="expected 100017"):
        play.PlayPublisher(fake, "com.suzent.mobile").publish(
            bundle, 100017, "0.7.2", NOTES, "alpha"
        )


def test_release_notes_respect_play_limit() -> None:
    text = play.whats_new("- " + "x" * 900, play.RELEASE_NOTES_LIMIT)
    assert len(text) == 500 and text.endswith("…")


def test_access_token_signs_a_verifiable_assertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    seen: dict[str, Any] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token": "tok"}'

    def fake_urlopen(url: str, data: bytes, timeout: int) -> Response:
        seen["url"] = url
        seen["form"] = dict(play.urllib.parse.parse_qsl(data.decode()))
        return Response()

    monkeypatch.setattr(play.urllib.request, "urlopen", fake_urlopen)
    account = {
        "client_email": "bot@example.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.example/token",
    }
    assert play.access_token(account, 1_000) == "tok"
    header, claims, signature = seen["form"]["assertion"].split(".")

    def decode(part: str) -> bytes:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))

    payload = json.loads(decode(claims))
    assert payload["iss"] == account["client_email"]
    assert payload["scope"] == play.SCOPE and payload["aud"] == account["token_uri"]
    key.public_key().verify(
        decode(signature),
        f"{header}.{claims}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
