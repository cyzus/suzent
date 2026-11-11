"""Submit an uploaded iOS build for App Store review, released automatically on approval."""

import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

API = "https://api.appstoreconnect.apple.com"
WHATS_NEW_LIMIT = 4000
EDITABLE_STATES = {
    "PREPARE_FOR_SUBMISSION",
    "DEVELOPER_REJECTED",
    "REJECTED",
    "METADATA_REJECTED",
    "INVALID_BINARY",
    "READY_FOR_REVIEW",
}
# Only versions nobody has submitted yet may be renamed to the release version.
RENAMABLE_STATES = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED"}

type Json = dict[str, Any]
type Transport = Callable[[str, str, Json | None], Json]


class AppStoreError(RuntimeError):
    pass


def whats_new(notes: str, limit: int = WHATS_NEW_LIMIT) -> str:
    """Convert a mobile changelog section into plain store release notes."""
    section = re.search(r"^### Release notes\s*\n(.*?)(?=^### |\Z)", notes, re.M | re.S)
    text = section[1] if section else notes
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = []
    for line in text.splitlines():
        line = line.rstrip()
        if line.lstrip().startswith("#"):
            continue
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"(\*\*|__|`)", "", line)
        line = re.sub(r"^\s*[-*]\s+", "• ", line)
        lines.append(line)
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if len(result) > limit:
        result = result[: limit - 1].rstrip() + "…"
    return result


def der_to_raw_signature(der: bytes, size: int = 32) -> bytes:
    """Convert an ASN.1 DER ECDSA signature into the JOSE r||s form."""
    if len(der) < 8 or der[0] != 0x30:
        raise ValueError("Not a DER ECDSA signature")
    offset = 3 if der[1] & 0x80 else 2
    parts = []
    for _ in range(2):
        if der[offset] != 0x02:
            raise ValueError("Malformed DER integer")
        length = der[offset + 1]
        value = der[offset + 2 : offset + 2 + length].lstrip(b"\x00")
        if len(value) > size:
            raise ValueError("Signature component too long")
        parts.append(value.rjust(size, b"\x00"))
        offset += 2 + length
    return b"".join(parts)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_token(key_path: Path, key_id: str, issuer_id: str, now: int) -> str:
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    payload = {
        "iss": issuer_id,
        "iat": now,
        "exp": now + 19 * 60,
        "aud": "appstoreconnect-v1",
    }
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":")).encode())
        for part in (header, payload)
    )
    der = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=signing_input.encode(),
        capture_output=True,
        check=True,
    ).stdout
    return f"{signing_input}.{_b64url(der_to_raw_signature(der))}"


def http_transport(token: Callable[[], str]) -> Transport:
    def send(method: str, path: str, body: Json | None) -> Json:
        request = urllib.request.Request(
            API + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {token()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise AppStoreError(f"{method} {path} failed with {error.code}: {detail}")
        return json.loads(raw) if raw else {}

    return send


class AppStoreSubmitter:
    def __init__(
        self,
        send: Transport,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.send = send
        self.sleep = sleep
        self.clock = clock

    def get(self, path: str, **query: str) -> Json:
        if query:
            path += "?" + urllib.parse.urlencode(query, safe="[],")
        return self.send("GET", path, None)

    def app_id(self, bundle_id: str) -> str:
        apps = self.get("/v1/apps", **{"filter[bundleId]": bundle_id})["data"]
        if not apps:
            raise AppStoreError(f"No App Store Connect app for {bundle_id}")
        return apps[0]["id"]

    def wait_for_build(
        self, app: str, version: str, build: int, timeout: float, interval: float
    ) -> str:
        deadline = self.clock() + timeout
        while True:
            builds = self.get(
                "/v1/builds",
                **{
                    "filter[app]": app,
                    "filter[version]": str(build),
                    "filter[preReleaseVersion.version]": version,
                    "filter[preReleaseVersion.platform]": "IOS",
                },
            )["data"]
            state = builds[0]["attributes"]["processingState"] if builds else None
            if state == "VALID":
                return builds[0]["id"]
            if state in {"FAILED", "INVALID"}:
                raise AppStoreError(f"Build {version} ({build}) processing is {state}")
            if self.clock() >= deadline:
                raise AppStoreError(
                    f"Build {version} ({build}) was not processed in time (state: {state or 'not found'})"
                )
            print(f"Waiting for build {version} ({build}): {state or 'not found yet'}")
            self.sleep(interval)

    def _versions(self, app: str, **query: str) -> list[Json]:
        return self.get(
            f"/v1/apps/{app}/appStoreVersions",
            **{"filter[platform]": "IOS", **query},
        )["data"]

    def prepare_version(self, app: str, version: str) -> Json | None:
        """Return the editable version to submit, or None when it is already past submission."""
        existing = self._versions(app, **{"filter[versionString]": version})
        if existing:
            current = existing[0]
            state = current["attributes"].get("appVersionState")
            if state not in EDITABLE_STATES:
                print(f"Version {version} is already {state}; nothing to submit")
                return None
            return current
        pending = self._versions(
            app, **{"filter[appVersionState]": ",".join(sorted(RENAMABLE_STATES))}
        )
        if pending:
            current = pending[0]
            print(
                f"Reusing unsubmitted version {current['attributes']['versionString']} as {version}"
            )
            return self.send(
                "PATCH",
                f"/v1/appStoreVersions/{current['id']}",
                {
                    "data": {
                        "type": "appStoreVersions",
                        "id": current["id"],
                        "attributes": {"versionString": version},
                    }
                },
            )["data"]
        print(f"Creating App Store version {version}")
        return self.send(
            "POST",
            "/v1/appStoreVersions",
            {
                "data": {
                    "type": "appStoreVersions",
                    "attributes": {
                        "platform": "IOS",
                        "versionString": version,
                        "releaseType": "AFTER_APPROVAL",
                    },
                    "relationships": {"app": {"data": {"type": "apps", "id": app}}},
                }
            },
        )["data"]

    def configure_version(
        self, version_id: str, build_id: str, notes: str | None
    ) -> None:
        self.send(
            "PATCH",
            f"/v1/appStoreVersions/{version_id}",
            {
                "data": {
                    "type": "appStoreVersions",
                    "id": version_id,
                    "attributes": {"releaseType": "AFTER_APPROVAL"},
                    "relationships": {
                        "build": {"data": {"type": "builds", "id": build_id}}
                    },
                }
            },
        )
        if notes is None:
            print("First App Store version: What's New is not available, skipping")
            return
        localizations = self.get(
            f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations"
        )["data"]
        if not localizations:
            print("::warning::Version has no localizations; What's New was not set")
        for localization in localizations:
            self.send(
                "PATCH",
                f"/v1/appStoreVersionLocalizations/{localization['id']}",
                {
                    "data": {
                        "type": "appStoreVersionLocalizations",
                        "id": localization["id"],
                        "attributes": {"whatsNew": notes},
                    }
                },
            )

    def submit(self, app: str, version_id: str) -> None:
        open_submissions = self.get(
            "/v1/reviewSubmissions",
            **{
                "filter[app]": app,
                "filter[platform]": "IOS",
                "filter[state]": "READY_FOR_REVIEW,UNRESOLVED_ISSUES,WAITING_FOR_REVIEW,IN_REVIEW",
            },
        )["data"]
        states = {item["attributes"]["state"] for item in open_submissions}
        if states & {"UNRESOLVED_ISSUES", "WAITING_FOR_REVIEW", "IN_REVIEW"}:
            raise AppStoreError(
                f"Another iOS review submission is open ({', '.join(sorted(states))}); "
                "resolve or cancel it in App Store Connect, then rerun this job"
            )
        if open_submissions:
            submission = open_submissions[0]["id"]
            items = self.get(
                f"/v1/reviewSubmissions/{submission}/items", include="appStoreVersion"
            )["data"]
            included = any(
                (
                    item.get("relationships", {}).get("appStoreVersion", {}).get("data")
                    or {}
                ).get("id")
                == version_id
                for item in items
            )
        else:
            submission = self.send(
                "POST",
                "/v1/reviewSubmissions",
                {
                    "data": {
                        "type": "reviewSubmissions",
                        "attributes": {"platform": "IOS"},
                        "relationships": {"app": {"data": {"type": "apps", "id": app}}},
                    }
                },
            )["data"]["id"]
            included = False
        if not included:
            self.send(
                "POST",
                "/v1/reviewSubmissionItems",
                {
                    "data": {
                        "type": "reviewSubmissionItems",
                        "relationships": {
                            "reviewSubmission": {
                                "data": {"type": "reviewSubmissions", "id": submission}
                            },
                            "appStoreVersion": {
                                "data": {"type": "appStoreVersions", "id": version_id}
                            },
                        },
                    }
                },
            )
        self.send(
            "PATCH",
            f"/v1/reviewSubmissions/{submission}",
            {
                "data": {
                    "type": "reviewSubmissions",
                    "id": submission,
                    "attributes": {"submitted": True},
                }
            },
        )

    def run(
        self,
        bundle_id: str,
        version: str,
        build: int,
        notes: str,
        timeout: float = 3600,
        interval: float = 30,
    ) -> bool:
        app = self.app_id(bundle_id)
        build_id = self.wait_for_build(app, version, build, timeout, interval)
        current = self.prepare_version(app, version)
        if current is None:
            return False
        # Apple rejects What's New on an app's first App Store version.
        first = all(
            item["id"] == current["id"] for item in self._versions(app, limit="2")
        )
        self.configure_version(
            current["id"], build_id, None if first else whats_new(notes)
        )
        self.submit(app, current["id"])
        print(
            f"Submitted {version} ({build}) for review; it releases automatically on approval"
        )
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="Directory with metadata.json and notes.md from mobile_release.py",
    )
    parser.add_argument("--bundle-id", default="com.suzent.mobile")
    parser.add_argument("--timeout-minutes", type=float, default=60)
    args = parser.parse_args()
    metadata = json.loads((args.metadata / "metadata.json").read_text(encoding="utf-8"))
    notes = (args.metadata / "notes.md").read_text(encoding="utf-8")
    for name in (
        "APP_STORE_CONNECT_KEY_BASE64",
        "APP_STORE_CONNECT_KEY_ID",
        "APP_STORE_CONNECT_ISSUER_ID",
    ):
        if not os.environ.get(name):
            raise SystemExit(f"::error::Missing {name} in mobile-release environment")
    with tempfile.TemporaryDirectory() as folder:
        key_path = Path(folder) / "AuthKey.p8"
        key_path.write_bytes(
            base64.b64decode(os.environ["APP_STORE_CONNECT_KEY_BASE64"], validate=True)
        )
        key_path.chmod(0o600)
        cached: dict[str, Any] = {"token": "", "at": 0}

        def token() -> str:
            now = int(time.time())
            if now - cached["at"] > 15 * 60:
                cached["token"] = make_token(
                    key_path,
                    os.environ["APP_STORE_CONNECT_KEY_ID"],
                    os.environ["APP_STORE_CONNECT_ISSUER_ID"],
                    now,
                )
                cached["at"] = now
            return cached["token"]

        AppStoreSubmitter(http_transport(token)).run(
            args.bundle_id,
            str(metadata["version"]),
            int(metadata["build"]),
            notes,
            timeout=args.timeout_minutes * 60,
        )


if __name__ == "__main__":
    main()
