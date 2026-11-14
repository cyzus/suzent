"""OAuth2 loopback sign-in and token refresh for Google Workspace and Microsoft 365.

Uses the standard desktop mail-client OAuth2 loopback flow (RFC 8252):
1. Bind an ephemeral local HTTP listener on ``127.0.0.1:<port>``.
2. Return the authorization URL so the frontend opens the system browser.
3. Receive the authorization code on ``127.0.0.1:<port>``, exchange it with
   PKCE for ``access_token`` + ``refresh_token``, verify IMAP/SMTP with
   himalaya, and store the tokens in Suzent's secret store.
4. Before any mail operation, refresh the access token automatically when it is
   within 60 seconds of expiry.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal

from suzent.logger import get_logger

from . import accounts as mail_accounts
from . import mailbox
from .accounts import MailAccount, MailAccountInput
from .himalaya import MailError
from .providers import OAuthProvider

logger = get_logger(__name__)

SIGN_IN_TIMEOUT_SECONDS = 300.0
TOKEN_EXPIRY_GRACE_SECONDS = 60.0


@dataclass(frozen=True)
class OAuthIssuer:
    id: OAuthProvider
    client_id: str
    client_secret: str | None
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    use_pkce: bool = True


# Public desktop mail-client OAuth2 registrations (Mozilla Thunderbird MPL-2.0)
# that are pre-allowlisted by institutional Google Workspace (e.g. UC Berkeley
# bMail) and Microsoft 365 / Exchange Online tenants for IMAP + SMTP XOAUTH2.
ISSUERS: dict[OAuthProvider, OAuthIssuer] = {
    "google": OAuthIssuer(
        id="google",
        client_id="406964657835-aq8lmia8j95dhl1a2bvharmfk3t1hgqj.apps.googleusercontent.com",
        client_secret="kSmqreRr0qwBWJgbf5Y-PjSU",
        authorize_url="https://accounts.google.com/o/oauth2/auth",
        token_url="https://www.googleapis.com/oauth2/v3/token",
        scopes=("https://mail.google.com/",),
        use_pkce=True,
    ),
    "microsoft": OAuthIssuer(
        id="microsoft",
        client_id="9e5f94bc-e8a4-4e73-b8be-63364c29d753",
        client_secret=None,
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scopes=(
            "https://outlook.office.com/IMAP.AccessAsUser.All",
            "https://outlook.office.com/SMTP.Send",
            "offline_access",
        ),
        use_pkce=True,
    ),
}

OAuthState = Literal["idle", "waiting", "signed_in", "failed"]


@dataclass
class MailOAuthSession:
    state: OAuthState = "idle"
    email: str = ""
    provider: str = ""
    authorize_url: str | None = None
    error: str | None = None
    account_id: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "email": self.email,
            "provider": self.provider,
            "authorizeUrl": self.authorize_url,
            "error": self.error,
            "accountId": self.account_id,
        }


_current_session: MailOAuthSession | None = None


def current_status() -> MailOAuthSession | None:
    return _current_session


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _post_token_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(body)
            desc = err_data.get("error_description") or err_data.get("error") or body
        except ValueError:
            desc = body or str(exc)
        raise MailError(f"OAuth token exchange failed: {desc[:300]}") from exc
    except OSError as exc:
        raise MailError(f"Could not reach OAuth token server: {exc}") from exc

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise MailError("OAuth server returned invalid JSON") from exc
    if not isinstance(data, dict) or "error" in data:
        desc = (
            data.get("error_description") or data.get("error")
            if isinstance(data, dict)
            else "unknown error"
        )
        raise MailError(f"OAuth token error: {desc}")
    return data


async def exchange_code(
    issuer: OAuthIssuer,
    code: str,
    redirect_uri: str,
    code_verifier: str | None,
) -> dict[str, Any]:
    form: dict[str, str] = {
        "client_id": issuer.client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    if issuer.client_secret:
        form["client_secret"] = issuer.client_secret
    if code_verifier:
        form["code_verifier"] = code_verifier
    result = await asyncio.to_thread(_post_token_form, issuer.token_url, form)
    now = time.time()
    expires_in = float(result.get("expires_in") or 3600)
    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": now + expires_in,
        "oauth_provider": issuer.id,
    }


async def refresh_access_token(
    issuer: OAuthIssuer, refresh_token: str
) -> dict[str, Any]:
    form: dict[str, str] = {
        "client_id": issuer.client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if issuer.client_secret:
        form["client_secret"] = issuer.client_secret
    result = await asyncio.to_thread(_post_token_form, issuer.token_url, form)
    now = time.time()
    expires_in = float(result.get("expires_in") or 3600)
    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token") or refresh_token,
        "expires_at": now + expires_in,
        "oauth_provider": issuer.id,
    }


async def ensure_access_token(account: MailAccount) -> str:
    """Return a valid access token for ``account``, refreshing if expired."""
    tokens = mail_accounts.get_oauth_tokens(account)
    if not tokens:
        raise LookupError(
            f"OAuth credentials for mail account '{account.id}' are missing; ask the "
            "user to sign in again in Settings → Services → Email."
        )
    access_token = str(tokens.get("access_token") or "")
    refresh_token = str(tokens.get("refresh_token") or "")
    expires_at = float(tokens.get("expires_at") or 0)
    if access_token and expires_at - TOKEN_EXPIRY_GRACE_SECONDS > time.time():
        return access_token
    if not refresh_token:
        if access_token:
            return access_token
        raise LookupError(
            f"OAuth session for '{account.id}' expired; ask the user to sign in "
            "again in Settings → Services → Email."
        )
    issuer_id = account.oauth_provider or tokens.get("oauth_provider") or "google"
    issuer = ISSUERS.get(issuer_id)  # type: ignore[arg-type]
    if issuer is None:
        raise MailError(f"Unsupported OAuth provider '{issuer_id}'")
    refreshed = await refresh_access_token(issuer, refresh_token)
    mail_accounts.set_oauth_tokens(account, refreshed)
    return str(refreshed["access_token"])


_HTML_PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Suzent Mail Sign-In</title>
  <style>
    body {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
           display: flex; align-items: center; justify-content: center;
           min-height: 90vh; margin: 0; background: #fafafa; color: #111; }}
    .card {{ border: 3px solid #111; background: #fff; padding: 24px 32px;
             max-width: 460px; box-shadow: 6px 6px 0 #111; }}
    h1 {{ font-size: 16px; margin: 0 0 8px; }}
    p {{ font-size: 13px; margin: 0; color: #444; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{title}</h1>
    <p>{body}</p>
  </div>
</body>
</html>
"""


def _http_response(status: str, title: str, body: str) -> bytes:
    html = _HTML_PAGE.format(title=title, body=body).encode("utf-8")
    headers = (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(html)}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    return headers + html


async def start_oauth_sign_in(data: MailAccountInput) -> MailOAuthSession:
    """Start a loopback OAuth2 browser sign-in for a mail account."""
    global _current_session
    if _current_session is not None and _current_session.task is not None:
        _current_session.task.cancel()

    data.auth_type = "xoauth2"
    account = mail_accounts.build_account(data)
    assert account.oauth_provider is not None
    issuer = ISSUERS[account.oauth_provider]

    state_token = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair() if issuer.use_pkce else (None, None)
    loop = asyncio.get_running_loop()
    code_future: asyncio.Future[str] = loop.create_future()

    async def _handle_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            parts = line.decode("utf-8", errors="replace").split(" ")
            path = parts[1] if len(parts) >= 2 else "/"
            parsed = urllib.parse.urlsplit(path)
            if parsed.path not in ("", "/"):
                writer.write(_http_response("404 Not Found", "Not Found", ""))
                await writer.drain()
                return
            params = urllib.parse.parse_qs(parsed.query)
            if "error" in params:
                err = params.get("error_description", params["error"])[0]
                if not code_future.done():
                    code_future.set_exception(MailError(f"Sign-in refused: {err}"))
                writer.write(
                    _http_response(
                        "400 Bad Request",
                        "Sign-in was not completed",
                        "You can close this tab and return to Suzent.",
                    )
                )
                await writer.drain()
                return
            if params.get("state", [None])[0] != state_token or "code" not in params:
                writer.write(
                    _http_response(
                        "400 Bad Request",
                        "Invalid callback",
                        "Missing or mismatched OAuth state.",
                    )
                )
                await writer.drain()
                return
            code = params["code"][0]
            if not code_future.done():
                code_future.set_result(code)
            writer.write(
                _http_response(
                    "200 OK",
                    "Signed in to Suzent",
                    "Suzent is verifying your mailbox connection. You can close this tab.",
                )
            )
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(_handle_client, host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    redirect_uri = f"http://127.0.0.1:{port}"

    query: dict[str, str] = {
        "response_type": "code",
        "client_id": issuer.client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(issuer.scopes),
        "state": state_token,
        "login_hint": account.email,
    }
    if issuer.id == "google":
        query["access_type"] = "offline"
        query["prompt"] = "consent"
    if challenge:
        query["code_challenge_method"] = "S256"
        query["code_challenge"] = challenge

    authorize_url = f"{issuer.authorize_url}?{urllib.parse.urlencode(query)}"
    session = MailOAuthSession(
        state="waiting",
        email=account.email,
        provider=account.provider,
        authorize_url=authorize_url,
        account_id=account.id,
    )
    _current_session = session

    async def _wait_and_complete() -> None:
        try:
            async with server:
                code = await asyncio.wait_for(
                    code_future, timeout=SIGN_IN_TIMEOUT_SECONDS
                )
            token_payload = await exchange_code(issuer, code, redirect_uri, verifier)
            probe = await mailbox.check(account, token_payload["access_token"])
            if not probe.get("ok"):
                raise MailError(str(probe.get("error") or "Mailbox check failed"))
            mail_accounts.upsert_oauth_account(account, token_payload)
            session.state = "signed_in"
            session.error = None
        except asyncio.CancelledError:
            session.state = "failed"
            session.error = "Sign-in was cancelled."
            raise
        except asyncio.TimeoutError:
            session.state = "failed"
            session.error = "Timed out waiting for browser sign-in."
        except Exception as exc:
            session.state = "failed"
            session.error = str(exc)[:300]
            logger.warning("Email OAuth sign-in failed for {}: {}", account.email, exc)

    session.task = asyncio.create_task(_wait_and_complete())
    return session
