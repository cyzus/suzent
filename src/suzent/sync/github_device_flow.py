from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

GITHUB_APP_CLIENT_ID = "Iv23li7x99E1YeSWhffQ"
GITHUB_APP_SLUG = "suzent"
GITHUB_APP_INSTALL_URL = f"https://github.com/apps/{GITHUB_APP_SLUG}/installations/new"

_DEVICE_CODE_URL = "https://github.com/login/device/code"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_SCOPE = "repo,read:user"

# How long a poll session lives in memory before we discard it (seconds).
_SESSION_TTL = 900


@dataclass
class DeviceFlowState:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    started_at: float


@dataclass(frozen=True)
class GitHubDeviceToken:
    access_token: str
    expires_in: int | None = None
    refresh_token: str | None = None
    refresh_token_expires_in: int | None = None
    token_type: str | None = None
    scope: str | None = None

    @classmethod
    def from_response(cls, data: dict) -> GitHubDeviceToken | None:
        access_token = str(data.get("access_token", "")).strip()
        if not access_token:
            return None
        return cls(
            access_token=access_token,
            expires_in=_optional_int(data.get("expires_in")),
            refresh_token=_optional_str(data.get("refresh_token")),
            refresh_token_expires_in=_optional_int(
                data.get("refresh_token_expires_in")
            ),
            token_type=_optional_str(data.get("token_type")),
            scope=_optional_str(data.get("scope")),
        )


class DeviceFlowError(RuntimeError):
    pass


class DeviceFlowExpired(DeviceFlowError):
    pass


class DeviceFlowDenied(DeviceFlowError):
    pass


def start() -> DeviceFlowState:
    """Request a device code from GitHub and return the display state."""
    response = httpx.post(
        _DEVICE_CODE_URL,
        data={"client_id": GITHUB_APP_CLIENT_ID, "scope": _SCOPE},
        headers={"Accept": "application/json"},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        detail = data.get("error_description", data["error"])
        raise DeviceFlowError(f"GitHub device flow start failed: {detail}")
    return DeviceFlowState(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_uri=data.get(
            "verification_uri", "https://github.com/login/device"
        ),
        expires_in=int(data.get("expires_in", 900)),
        interval=int(data.get("interval", 5)),
        started_at=time.monotonic(),
    )


def poll(state: DeviceFlowState) -> GitHubDeviceToken | None:
    """Poll once for an access token.

    Returns the token string when the user has approved, None when still pending.
    Raises DeviceFlowExpired / DeviceFlowDenied on terminal failures.
    """
    elapsed = time.monotonic() - state.started_at
    if elapsed >= state.expires_in:
        raise DeviceFlowExpired("Device flow authorization expired")

    response = httpx.post(
        _TOKEN_URL,
        data={
            "client_id": GITHUB_APP_CLIENT_ID,
            "device_code": state.device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
        headers={"Accept": "application/json"},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    error = data.get("error")
    if not error:
        return GitHubDeviceToken.from_response(data)

    if error == "authorization_pending":
        return None
    if error == "slow_down":
        # GitHub asks us to back off; caller should increase interval.
        state.interval = int(data.get("interval", state.interval + 5))
        return None
    if error == "expired_token":
        raise DeviceFlowExpired("Device flow authorization expired")
    if error == "access_denied":
        raise DeviceFlowDenied("User denied the authorization request")
    raise DeviceFlowError(
        f"Device flow poll error: {data.get('error_description', error)}"
    )


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
