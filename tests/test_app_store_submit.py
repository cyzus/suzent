import base64
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import load_pem_private_key

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/mobile/app_store_submit.py"
spec = importlib.util.spec_from_file_location("app_store_submit", SCRIPT)
assert spec is not None and spec.loader is not None
submit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(submit)

APP = "app-1"
BUILD = {"id": "build-1", "attributes": {"processingState": "VALID"}}


class FakeAppStore:
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, method: str, path: str, body: Any) -> Any:
        self.calls.append((method, path, body))
        for (route_method, prefix), response in self.routes.items():
            if method == route_method and path.startswith(prefix):
                return response(path) if callable(response) else response
        raise AssertionError(f"Unexpected {method} {path}")

    def paths(self, method: str) -> list[str]:
        return [path for m, path, _ in self.calls if m == method]

    def body(self, method: str, prefix: str) -> Any:
        return next(b for m, p, b in self.calls if m == method and p.startswith(prefix))


def routes(
    overrides: dict[tuple[str, str], Any] | None = None,
) -> dict[tuple[str, str], Any]:
    base: dict[tuple[str, str], Any] = {
        ("GET", "/v1/apps?"): {"data": [{"id": APP}]},
        ("GET", "/v1/builds"): {"data": [BUILD]},
        ("GET", f"/v1/apps/{APP}/appStoreVersions"): {"data": []},
        ("POST", "/v1/appStoreVersions"): {"data": {"id": "version-1"}},
        ("PATCH", "/v1/appStoreVersions/"): {"data": {"id": "version-1"}},
        ("GET", "/v1/appStoreVersions/version-1/appStoreVersionLocalizations"): {
            "data": [{"id": "loc-en"}, {"id": "loc-zh"}]
        },
        ("PATCH", "/v1/appStoreVersionLocalizations/"): {},
        ("GET", "/v1/reviewSubmissions?"): {"data": []},
        ("POST", "/v1/reviewSubmissions"): {"data": {"id": "sub-1"}},
        ("POST", "/v1/reviewSubmissionItems"): {"data": {"id": "item-1"}},
        ("PATCH", "/v1/reviewSubmissions/"): {},
    }
    base.update(overrides or {})
    return base


NOTES = (
    "<!-- highlights -->\n### Highlights\n\n- **Big** thing.\n<!-- /highlights -->\n\n"
    "### Release notes\n- Fix the `relay` [link](https://x.y).\n- Second note.\n"
)


def test_whats_new_uses_release_notes_as_plain_text() -> None:
    assert submit.whats_new(NOTES) == "• Fix the relay link.\n• Second note."


def test_whats_new_without_sections_and_length_limit() -> None:
    assert submit.whats_new("New release.\n") == "New release."
    long = submit.whats_new("- " + "x" * 5000)
    assert len(long) == submit.WHATS_NEW_LIMIT and long.endswith("…")


def test_creates_version_attaches_build_and_submits() -> None:
    fake = FakeAppStore(routes())
    assert submit.AppStoreSubmitter(fake).run(
        "com.suzent.mobile", "0.7.2", 100017, NOTES
    )

    created = fake.body("POST", "/v1/appStoreVersions")["data"]["attributes"]
    assert created == {
        "platform": "IOS",
        "versionString": "0.7.2",
        "releaseType": "AFTER_APPROVAL",
    }
    patch = fake.body("PATCH", "/v1/appStoreVersions/version-1")["data"]
    assert patch["relationships"]["build"]["data"]["id"] == "build-1"
    assert patch["attributes"]["releaseType"] == "AFTER_APPROVAL"
    assert fake.paths("PATCH")[1:3] == [
        "/v1/appStoreVersionLocalizations/loc-en",
        "/v1/appStoreVersionLocalizations/loc-zh",
    ]
    item = fake.body("POST", "/v1/reviewSubmissionItems")["data"]["relationships"]
    assert item["reviewSubmission"]["data"]["id"] == "sub-1"
    assert item["appStoreVersion"]["data"]["id"] == "version-1"
    final = fake.calls[-1]
    assert final[:2] == ("PATCH", "/v1/reviewSubmissions/sub-1")
    assert final[2]["data"]["attributes"] == {"submitted": True}
    builds_query = next(p for p in fake.paths("GET") if p.startswith("/v1/builds"))
    assert "filter[version]=100017" in builds_query
    assert "filter[preReleaseVersion.version]=0.7.2" in builds_query


def test_already_submitted_version_is_left_alone() -> None:
    existing = {
        "data": [
            {"id": "version-1", "attributes": {"appVersionState": "WAITING_FOR_REVIEW"}}
        ]
    }
    fake = FakeAppStore(routes({("GET", f"/v1/apps/{APP}/appStoreVersions"): existing}))
    assert not submit.AppStoreSubmitter(fake).run(
        "com.suzent.mobile", "0.7.2", 1, NOTES
    )
    assert fake.paths("POST") == [] and fake.paths("PATCH") == []


def test_renames_unsubmitted_version_instead_of_creating() -> None:
    def versions(path: str) -> Any:
        if "versionString" in path:
            return {"data": []}
        return {
            "data": [
                {
                    "id": "version-1",
                    "attributes": {
                        "versionString": "0.7.1",
                        "appVersionState": "PREPARE_FOR_SUBMISSION",
                    },
                }
            ]
        }

    fake = FakeAppStore(routes({("GET", f"/v1/apps/{APP}/appStoreVersions"): versions}))
    submit.AppStoreSubmitter(fake).run("com.suzent.mobile", "0.7.2", 1, NOTES)
    assert "/v1/appStoreVersions" not in fake.paths("POST")
    rename = fake.body("PATCH", "/v1/appStoreVersions/version-1")["data"]
    assert rename["attributes"] == {"versionString": "0.7.2"}


def test_reuses_open_submission_already_containing_version() -> None:
    fake = FakeAppStore(
        routes(
            {
                ("GET", "/v1/reviewSubmissions?"): {
                    "data": [
                        {"id": "sub-9", "attributes": {"state": "READY_FOR_REVIEW"}}
                    ]
                },
                ("GET", "/v1/reviewSubmissions/sub-9/items"): {
                    "data": [
                        {
                            "relationships": {
                                "appStoreVersion": {
                                    "data": {
                                        "type": "appStoreVersions",
                                        "id": "version-1",
                                    }
                                }
                            }
                        }
                    ]
                },
            }
        )
    )
    submit.AppStoreSubmitter(fake).run("com.suzent.mobile", "0.7.2", 1, NOTES)
    assert "/v1/reviewSubmissions" not in fake.paths("POST")
    assert "/v1/reviewSubmissionItems" not in fake.paths("POST")
    assert fake.calls[-1][1] == "/v1/reviewSubmissions/sub-9"


def test_open_rejected_submission_stops() -> None:
    fake = FakeAppStore(
        routes(
            {
                ("GET", "/v1/reviewSubmissions?"): {
                    "data": [
                        {"id": "sub-9", "attributes": {"state": "UNRESOLVED_ISSUES"}}
                    ]
                }
            }
        )
    )
    with pytest.raises(submit.AppStoreError, match="UNRESOLVED_ISSUES"):
        submit.AppStoreSubmitter(fake).run("com.suzent.mobile", "0.7.2", 1, NOTES)


def test_waits_for_processing_then_times_out() -> None:
    states = iter(
        [[], [{"id": "b", "attributes": {"processingState": "PROCESSING"}}], [BUILD]]
    )
    fake = FakeAppStore(
        routes({("GET", "/v1/builds"): lambda _: {"data": next(states)}})
    )
    slept: list[float] = []
    submitter = submit.AppStoreSubmitter(fake, sleep=slept.append, clock=lambda: 0)
    assert (
        submitter.wait_for_build(APP, "0.7.2", 1, timeout=100, interval=5) == "build-1"
    )
    assert slept == [5, 5]

    pending = {"data": [{"id": "b", "attributes": {"processingState": "PROCESSING"}}]}
    ticks = iter([0, 10])
    stuck = submit.AppStoreSubmitter(
        FakeAppStore(routes({("GET", "/v1/builds"): pending})),
        sleep=lambda _: None,
        clock=lambda: next(ticks),
    )
    with pytest.raises(submit.AppStoreError, match="not processed in time"):
        stuck.wait_for_build(APP, "0.7.2", 1, timeout=5, interval=5)


def test_failed_build_processing_raises() -> None:
    failed = {"data": [{"id": "b", "attributes": {"processingState": "INVALID"}}]}
    fake = FakeAppStore(routes({("GET", "/v1/builds"): failed}))
    with pytest.raises(submit.AppStoreError, match="INVALID"):
        submit.AppStoreSubmitter(fake).run("com.suzent.mobile", "0.7.2", 1, NOTES)


def test_token_is_a_verifiable_es256_jwt(tmp_path: Path) -> None:
    key_path = tmp_path / "AuthKey.p8"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "EC",
            "-pkeyopt",
            "ec_paramgen_curve:P-256",
            "-out",
            str(key_path),
        ],
        check=True,
        capture_output=True,
    )
    token = submit.make_token(key_path, "KEY123", "issuer-1", 1_000)
    header, payload, signature = token.split(".")

    def decode(part: str) -> bytes:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))

    assert json.loads(decode(header)) == {"alg": "ES256", "kid": "KEY123", "typ": "JWT"}
    claims = json.loads(decode(payload))
    assert claims["iss"] == "issuer-1" and claims["aud"] == "appstoreconnect-v1"
    assert claims["exp"] - claims["iat"] <= 20 * 60
    raw = decode(signature)
    assert len(raw) == 64
    der = encode_dss_signature(int.from_bytes(raw[:32]), int.from_bytes(raw[32:]))
    key = load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    key.public_key().verify(
        der, f"{header}.{payload}".encode(), ec.ECDSA(hashes.SHA256())
    )
