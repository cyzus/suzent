from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

GITHUB_APP_CLIENT_ID = "Iv23li7x99E1YeSWhffQ"

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


class DeviceFlowError(RuntimeError):
    pass


class DeviceFlowExpired(DeviceFlowError):
    pass


class DeviceFlowDenied(DeviceFlowError):
    pass


def start() -> DeviceFlowState:
    """Request a device code from GitHub and return the state the caller should display."""
    response = httpx.post(
        _DEVICE_CODE_URL,
        data={"client_id": GITHUB_APP_CLIENT_ID, "scope": _SCOPE},
        headers={"Accept": "application/json"},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise DeviceFlowError(
            f"GitHub device flow start failed: {data.get('error_description', data['error'])}"
        )
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


def poll(state: DeviceFlowState) -> str | None:
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
        token = data.get("access_token", "").strip()
        if token:
            return token
        return None

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
