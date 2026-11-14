"""Settings-page API, served at /plugins/email/api/<path>."""

from __future__ import annotations

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import accounts as mail_accounts
from . import mailbox, oauth
from .accounts import MailAccount, MailAccountInput
from .himalaya import MailError
from .providers import PROVIDERS


def _public(account: MailAccount) -> dict:
    data = account.model_dump()
    data["has_password"] = mail_accounts.has_credentials(account)
    return data


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


async def list_providers(request: Request) -> JSONResponse:
    return JSONResponse({"providers": [p.to_dict() for p in PROVIDERS.values()]})


async def list_accounts(request: Request) -> JSONResponse:
    session = oauth.current_status()
    return JSONResponse(
        {
            "accounts": [_public(a) for a in mail_accounts.list_accounts()],
            "oauthSignIn": session.to_dict() if session else None,
        }
    )


async def add_account(request: Request) -> JSONResponse:
    try:
        data = MailAccountInput.model_validate(await _body(request))
        account = mail_accounts.build_account(data)
    except (ValidationError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if mail_accounts.get_account(account.id) is not None:
        return JSONResponse({"error": "Account already exists"}, status_code=409)
    # Sign in before saving, so a wrong authorization code is caught while the
    # user is still looking at the form rather than on the agent's first use.
    try:
        probe = await mailbox.check(account, data.password)
    except MailError as e:
        probe = {"ok": False, "error": str(e)}
    if not probe["ok"]:
        return JSONResponse({"error": probe["error"], "probe": probe}, status_code=422)
    if not mail_accounts.add_account(account, data.password):
        return JSONResponse({"error": "Account already exists"}, status_code=409)
    return JSONResponse({"success": True, "account": _public(account), "probe": probe})


async def start_oauth(request: Request) -> JSONResponse:
    try:
        payload = await _body(request)
        payload["auth_type"] = "xoauth2"
        data = MailAccountInput.model_validate(payload)
        session = await oauth.start_oauth_sign_in(data)
    except (ValidationError, ValueError, MailError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"success": True, "oauthSignIn": session.to_dict()})


async def update_account(request: Request) -> JSONResponse:
    data = await _body(request)
    account_id = data.pop("id", None)
    if not account_id:
        return JSONResponse({"error": "Missing id"}, status_code=400)
    try:
        account = mail_accounts.update_account(account_id, **data)
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if account is None:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    return JSONResponse({"success": True, "account": _public(account)})


async def test_account(request: Request) -> JSONResponse:
    data = await _body(request)
    account = mail_accounts.get_account(str(data.get("id") or ""))
    if account is None:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    try:
        credential = await mail_accounts.resolve_credential(account)
        return JSONResponse(await mailbox.check(account, credential))
    except (LookupError, MailError) as e:
        return JSONResponse({"ok": False, "error": str(e)})


async def remove_account(request: Request) -> JSONResponse:
    data = await _body(request)
    if mail_accounts.remove_account(str(data.get("id") or "")):
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Account not found"}, status_code=404)
