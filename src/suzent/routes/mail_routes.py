"""Mailbox account management API routes."""

import asyncio

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.mail import accounts as mail_accounts
from suzent.mail.accounts import MailAccount, MailAccountInput
from suzent.mail.client import check_account
from suzent.mail.providers import PROVIDERS


def _public(account: MailAccount) -> dict:
    data = account.model_dump()
    data["has_password"] = bool(mail_accounts.get_password(account))
    return data


async def list_mail_providers(request: Request) -> JSONResponse:
    return JSONResponse({"providers": [p.to_dict() for p in PROVIDERS.values()]})


async def list_mail_accounts(request: Request) -> JSONResponse:
    return JSONResponse(
        {"accounts": [_public(a) for a in mail_accounts.list_accounts()]}
    )


async def add_mail_account(request: Request) -> JSONResponse:
    try:
        data = MailAccountInput.model_validate(await request.json())
        account = mail_accounts.build_account(data)
    except (ValidationError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # Sign in before saving, so a wrong authorization code is caught while the
    # user is still looking at the form rather than on the agent's first use.
    probe = await asyncio.to_thread(check_account, account, data.password)
    if not probe["ok"]:
        return JSONResponse({"error": probe["error"], "probe": probe}, status_code=422)
    if not mail_accounts.add_account(account, data.password):
        return JSONResponse({"error": "Account already exists"}, status_code=409)
    return JSONResponse({"success": True, "account": _public(account), "probe": probe})


async def update_mail_account(request: Request) -> JSONResponse:
    data = await request.json()
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


async def test_mail_account(request: Request) -> JSONResponse:
    data = await request.json()
    account = mail_accounts.get_account(data.get("id") or "")
    if account is None:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    password = mail_accounts.get_password(account)
    if not password:
        return JSONResponse({"ok": False, "error": "Password is missing"})
    return JSONResponse(await asyncio.to_thread(check_account, account, password))


async def remove_mail_account(request: Request) -> JSONResponse:
    data = await request.json()
    if mail_accounts.remove_account(data.get("id") or ""):
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Account not found"}, status_code=404)
