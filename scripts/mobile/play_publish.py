"""Upload a signed Android App Bundle to a Google Play track and roll it out."""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app_store_submit import whats_new  # noqa: E402

API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
UPLOAD_API = (
    "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications"
)
SCOPE = "https://www.googleapis.com/auth/androidpublisher"
RELEASE_NOTES_LIMIT = 500

type Json = dict[str, Any]
type Transport = Callable[[str, str, bytes | None, str], Json]


class PlayError(RuntimeError):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def access_token(account: Json, now: int) -> str:
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64url(
        json.dumps(
            {
                "iss": account["client_email"],
                "scope": SCOPE,
                "aud": account["token_uri"],
                "iat": now,
                "exp": now + 3600,
            }
        ).encode()
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".pem") as key:
        key.write(account["private_key"])
        key.flush()
        signature = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key.name],
            input=f"{header}.{claims}".encode(),
            capture_output=True,
            check=True,
        ).stdout
    form = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": f"{header}.{claims}.{_b64url(signature)}",
        }
    ).encode()
    try:
        with urllib.request.urlopen(account["token_uri"], form, timeout=60) as response:
            return json.load(response)["access_token"]
    except urllib.error.HTTPError as error:
        raise PlayError(
            f"Token exchange failed with {error.code}: {error.read().decode()}"
        )


def http_transport(token: str) -> Transport:
    def send(method: str, url: str, body: bytes | None, content_type: str) -> Json:
        request = urllib.request.Request(
            url,
            method=method,
            data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise PlayError(f"{method} {url} failed with {error.code}: {detail}")
        return json.loads(raw) if raw else {}

    return send


class PlayPublisher:
    def __init__(self, send: Transport, package: str) -> None:
        self.send = send
        self.package = package

    def _json(self, method: str, path: str, body: Json | None = None) -> Json:
        data = json.dumps(body).encode() if body is not None else None
        return self.send(
            method, f"{API}/{self.package}/{path}", data, "application/json"
        )

    def publish(
        self, bundle: Path, version_code: int, version: str, notes: str, track: str
    ) -> bool:
        edit = self._json("POST", "edits", {})["id"]
        try:
            current = self._json("GET", f"edits/{edit}/tracks/{track}")
            if any(
                str(version_code) in release.get("versionCodes", [])
                and release.get("status") == "completed"
                for release in current.get("releases", [])
            ):
                print(f"{version} ({version_code}) is already live on {track}")
                self._json("DELETE", f"edits/{edit}")
                return False
            uploaded = self._json("GET", f"edits/{edit}/bundles").get("bundles", [])
            if any(item["versionCode"] == version_code for item in uploaded):
                print(f"Bundle {version_code} was already uploaded; reusing it")
            else:
                print(f"Uploading {bundle.name}")
                result = self.send(
                    "POST",
                    f"{UPLOAD_API}/{self.package}/edits/{edit}/bundles?uploadType=media",
                    bundle.read_bytes(),
                    "application/octet-stream",
                )
                if result.get("versionCode") != version_code:
                    raise PlayError(
                        f"Uploaded bundle has version code {result.get('versionCode')}, expected {version_code}"
                    )
            languages = [
                listing["language"]
                for listing in self._json("GET", f"edits/{edit}/listings").get(
                    "listings", []
                )
            ] or ["en-US"]
            text = whats_new(notes, RELEASE_NOTES_LIMIT)
            self._json(
                "PUT",
                f"edits/{edit}/tracks/{track}",
                {
                    "track": track,
                    "releases": [
                        {
                            "name": version,
                            "versionCodes": [str(version_code)],
                            "status": "completed",
                            "releaseNotes": [
                                {"language": language, "text": text}
                                for language in languages
                            ],
                        }
                    ],
                },
            )
            self._json("POST", f"edits/{edit}:commit")
        except Exception:
            try:
                self._json("DELETE", f"edits/{edit}")
            except PlayError:
                pass
            raise
        print(f"Released {version} ({version_code}) to the {track} track")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="Directory with metadata.json and notes.md from mobile_release.py",
    )
    parser.add_argument("--track", default="alpha")
    parser.add_argument("--package", default="com.suzent.mobile")
    args = parser.parse_args()
    raw = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise SystemExit(
            "::error::Missing GOOGLE_PLAY_SERVICE_ACCOUNT_JSON in mobile-release environment"
        )
    metadata = json.loads((args.metadata / "metadata.json").read_text(encoding="utf-8"))
    token = access_token(json.loads(raw), int(time.time()))
    PlayPublisher(http_transport(token), args.package).publish(
        args.bundle,
        int(metadata["build"]),
        str(metadata["version"]),
        (args.metadata / "notes.md").read_text(encoding="utf-8"),
        args.track,
    )


if __name__ == "__main__":
    main()
