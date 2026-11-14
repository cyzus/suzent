"""Mailbox accounts: settings in a JSON file, credentials in the secret store.

Settings live at USER_CONFIG_DIR/mail_accounts.json, keyed by account id.
Passwords and OAuth2 tokens never touch that file: they go to the plugin's
secret store, which Suzent keeps out of ``os.environ`` so shell commands the
agent runs cannot read them, and reach himalaya only for the run that needs
them.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from suzent.config import USER_CONFIG_DIR
from suzent.logger import get_logger
from suzent.plugins.context import PluginSecrets

from .providers import OAuthProvider, SmtpSecurity, get_provider

logger = get_logger(__name__)

_ACCOUNTS_FILE = USER_CONFIG_DIR / "mail_accounts.json"

_secrets: PluginSecrets | None = None

AuthType = Literal["password", "xoauth2"]


def use_secrets(secrets: PluginSecrets) -> None:
    global _secrets
    _secrets = secrets


def _store() -> PluginSecrets:
    if _secrets is None:
        raise RuntimeError("the email plugin is not loaded")
    return _secrets


class MailAccount(BaseModel):
    id: str
    email: str
    display_name: str = ""
    provider: str = "custom"
    auth_type: AuthType = "password"
    oauth_provider: OAuthProvider | None = None
    username: str = ""
    imap_host: str
    imap_port: int = 993
    smtp_host: str
    smtp_port: int = 465
    smtp_security: SmtpSecurity = "ssl"
    needs_imap_id: bool = False
    no_sasl_ir: bool = False
    append_sent: bool = True
    # Off until the user turns it on: drafts are the default way to write mail.
    allow_send: bool = False
    # Off until the user turns it on: report new inbox mail to the Mailbox.
    watch_inbox: bool = False

    @property
    def login(self) -> str:
        return self.username or self.email


class MailAccountInput(BaseModel):
    """What the settings page sends to create an account."""

    email: str = Field(min_length=3)
    password: str = ""
    provider: str = "custom"
    auth_type: AuthType = "password"
    oauth_provider: OAuthProvider | None = None
    id: str | None = None
    display_name: str = ""
    username: str = ""
    imap_host: str = ""
    imap_port: int | None = None
    smtp_host: str = ""
    smtp_port: int | None = None
    smtp_security: SmtpSecurity | None = None
    allow_send: bool = False


def _secret_name(account_id: str) -> str:
    return "password:" + re.sub(r"[^a-z0-9._@-]+", "-", account_id.lower())


def _oauth_secret_name(account_id: str) -> str:
    return "oauth:" + re.sub(r"[^a-z0-9._@-]+", "-", account_id.lower())


def default_account_id(email: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", email.lower()).strip("-") or "mail"


def build_account(data: MailAccountInput) -> MailAccount:
    """Fill server settings from the provider preset where the input left them out."""
    provider = get_provider(data.provider) or get_provider("custom")
    assert provider is not None
    if data.auth_type == "password" and provider.oauth_only:
        raise ValueError(
            f"{provider.label} no longer accepts passwords over IMAP and needs "
            "browser sign-in (OAuth2)."
        )
    if data.auth_type == "password" and not data.password:
        raise ValueError("Password or app password is required.")
    oauth_provider = data.oauth_provider or provider.oauth_provider
    if data.auth_type == "xoauth2" and not oauth_provider:
        raise ValueError("This provider does not support OAuth sign-in.")
    imap_host = data.imap_host.strip() or provider.imap_host
    smtp_host = data.smtp_host.strip() or provider.smtp_host
    if not imap_host or not smtp_host:
        raise ValueError("IMAP and SMTP servers are required for this provider.")
    return MailAccount(
        id=(data.id or "").strip() or default_account_id(data.email),
        email=data.email.strip(),
        display_name=data.display_name.strip(),
        provider=provider.id,
        auth_type=data.auth_type,
        oauth_provider=oauth_provider if data.auth_type == "xoauth2" else None,
        username=data.username.strip(),
        imap_host=imap_host,
        imap_port=data.imap_port or provider.imap_port,
        smtp_host=smtp_host,
        smtp_port=data.smtp_port or provider.smtp_port,
        smtp_security=data.smtp_security or provider.smtp_security,
        needs_imap_id=provider.needs_imap_id,
        no_sasl_ir=provider.no_sasl_ir,
        append_sent=not provider.server_saves_sent,
        allow_send=data.allow_send,
    )


def _load() -> dict[str, dict[str, Any]]:
    if not _ACCOUNTS_FILE.exists():
        return {}
    try:
        data = json.loads(_ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"Could not read {_ACCOUNTS_FILE.name}: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def _save(accounts: dict[str, dict[str, Any]]) -> None:
    _ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=_ACCOUNTS_FILE.parent, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp:
        json.dump(accounts, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.replace(_ACCOUNTS_FILE)


def list_accounts() -> list[MailAccount]:
    accounts = []
    for entry in _load().values():
        try:
            accounts.append(MailAccount.model_validate(entry))
        except ValueError as e:
            logger.warning(f"Skipping invalid mail account entry: {e}")
    return accounts


def get_account(account_id: str) -> MailAccount | None:
    entry = _load().get(account_id)
    return MailAccount.model_validate(entry) if entry else None


def add_account(account: MailAccount, password: str = "") -> bool:
    accounts = _load()
    if account.id in accounts:
        return False
    if password:
        _store().set(_secret_name(account.id), password)
    accounts[account.id] = account.model_dump()
    _save(accounts)
    logger.info("Added a mail account")
    return True


def upsert_oauth_account(account: MailAccount, token_payload: dict[str, Any]) -> None:
    """Save or update an OAuth2 mail account and its token bundle."""
    accounts = _load()
    existing = accounts.get(account.id)
    if existing:
        account.allow_send = bool(existing.get("allow_send", account.allow_send))
        account.watch_inbox = bool(existing.get("watch_inbox", account.watch_inbox))
    set_oauth_tokens(account, token_payload)
    accounts[account.id] = account.model_dump()
    _save(accounts)
    logger.info("Saved OAuth mail account")


def update_account(account_id: str, **changes: Any) -> MailAccount | None:
    """Change stored settings; a ``password`` change goes to the secret store."""
    accounts = _load()
    entry = accounts.get(account_id)
    if not entry:
        return None
    password = changes.pop("password", None)
    allowed = set(MailAccount.model_fields) - {"id"}
    entry.update({k: v for k, v in changes.items() if k in allowed})
    account = MailAccount.model_validate(entry)
    if password:
        _store().set(_secret_name(account_id), password)
    accounts[account_id] = account.model_dump()
    _save(accounts)
    return account


def remove_account(account_id: str) -> bool:
    accounts = _load()
    if account_id not in accounts:
        return False
    _store().delete(_secret_name(account_id))
    _store().delete(_oauth_secret_name(account_id))
    del accounts[account_id]
    _save(accounts)
    logger.info("Removed a mail account")
    return True


def get_password(account: MailAccount) -> str | None:
    return _store().get(_secret_name(account.id))


def get_oauth_tokens(account: MailAccount) -> dict[str, Any] | None:
    raw = _store().get(_oauth_secret_name(account.id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def set_oauth_tokens(account: MailAccount, payload: dict[str, Any]) -> None:
    _store().set(_oauth_secret_name(account.id), json.dumps(payload))


def has_credentials(account: MailAccount) -> bool:
    if account.auth_type == "xoauth2":
        tokens = get_oauth_tokens(account)
        return bool(
            tokens and (tokens.get("refresh_token") or tokens.get("access_token"))
        )
    return bool(get_password(account))


async def resolve_credential(account: MailAccount) -> str:
    """Return the password or a fresh OAuth2 access token for ``account``."""
    if account.auth_type == "xoauth2":
        from . import oauth

        return await oauth.ensure_access_token(account)
    password = get_password(account)
    if not password:
        raise LookupError(
            f"The password for mail account '{account.id}' is missing; ask the user "
            "to re-enter it in Settings → Services → Email."
        )
    return password


def resolve_account(account_id: str | None) -> MailAccount:
    """The named account, or the only one when none is named.

    Raises LookupError with a message the agent can act on.
    """
    accounts = list_accounts()
    if not accounts:
        raise LookupError(
            "No mailbox is connected. Ask the user to add one in "
            "Settings → Services → Email."
        )
    if account_id:
        for account in accounts:
            if account_id in (account.id, account.email):
                return account
        raise LookupError(
            f"No mail account '{account_id}'. Connected: "
            + ", ".join(a.id for a in accounts)
        )
    if len(accounts) == 1:
        return accounts[0]
    raise LookupError(
        "Several mailboxes are connected; pass `account`. Connected: "
        + ", ".join(f"{a.id} ({a.email})" for a in accounts)
    )
