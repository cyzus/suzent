"""Mailbox accounts: settings in a JSON file, passwords in the secret store.

Settings live at USER_CONFIG_DIR/mail_accounts.json, keyed by account id. The
password never touches that file: it goes to the keyring (or the encrypted
SQLite fallback) under a ``SUZENT_MAIL_`` key, which the secret manager keeps
out of ``os.environ`` so shell commands the agent runs cannot read it.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from suzent.config import USER_CONFIG_DIR
from suzent.logger import get_logger
from suzent.mail.providers import SmtpSecurity, get_provider

logger = get_logger(__name__)

_ACCOUNTS_FILE = USER_CONFIG_DIR / "mail_accounts.json"

MAIL_SECRET_PREFIX = "SUZENT_MAIL_"


class MailAccount(BaseModel):
    id: str
    email: str
    display_name: str = ""
    provider: str = "custom"
    username: str = ""
    imap_host: str
    imap_port: int = 993
    smtp_host: str
    smtp_port: int = 465
    smtp_security: SmtpSecurity = "ssl"
    needs_imap_id: bool = False
    append_sent: bool = True
    # Off until the user turns it on: drafts are the default way to write mail.
    allow_send: bool = False

    @property
    def login(self) -> str:
        return self.username or self.email

    @property
    def secret_key(self) -> str:
        return secret_key_for(self.id)


class MailAccountInput(BaseModel):
    """What the settings page sends to create an account."""

    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    provider: str = "custom"
    id: str | None = None
    display_name: str = ""
    username: str = ""
    imap_host: str = ""
    imap_port: int | None = None
    smtp_host: str = ""
    smtp_port: int | None = None
    smtp_security: SmtpSecurity | None = None
    allow_send: bool = False


def secret_key_for(account_id: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", account_id.upper()).strip("_")
    return f"{MAIL_SECRET_PREFIX}{slug}_PASSWORD"


def default_account_id(email: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", email.lower()).strip("-") or "mail"


def build_account(data: MailAccountInput) -> MailAccount:
    """Fill server settings from the provider preset where the input left them out."""
    provider = get_provider(data.provider) or get_provider("custom")
    assert provider is not None
    if provider.oauth_only:
        raise ValueError(
            f"{provider.label} no longer accepts passwords over IMAP and needs "
            "Microsoft sign-in, which Suzent does not support yet."
        )
    imap_host = data.imap_host.strip() or provider.imap_host
    smtp_host = data.smtp_host.strip() or provider.smtp_host
    if not imap_host or not smtp_host:
        raise ValueError("IMAP and SMTP servers are required for this provider.")
    return MailAccount(
        id=(data.id or "").strip() or default_account_id(data.email),
        email=data.email.strip(),
        display_name=data.display_name.strip(),
        provider=provider.id,
        username=data.username.strip(),
        imap_host=imap_host,
        imap_port=data.imap_port or provider.imap_port,
        smtp_host=smtp_host,
        smtp_port=data.smtp_port or provider.smtp_port,
        smtp_security=data.smtp_security or provider.smtp_security,
        needs_imap_id=provider.needs_imap_id,
        append_sent=not provider.server_saves_sent,
        allow_send=data.allow_send,
    )


def _load() -> dict[str, dict[str, Any]]:
    if not _ACCOUNTS_FILE.exists():
        return {}
    try:
        data = json.loads(_ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
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
        except Exception as e:
            logger.warning(f"Skipping invalid mail account entry: {e}")
    return accounts


def get_account(account_id: str) -> MailAccount | None:
    entry = _load().get(account_id)
    return MailAccount.model_validate(entry) if entry else None


def add_account(account: MailAccount, password: str) -> bool:
    accounts = _load()
    if account.id in accounts:
        return False
    from suzent.core.secrets import get_secret_manager

    get_secret_manager().set_backend_only(account.secret_key, password)
    accounts[account.id] = account.model_dump()
    _save(accounts)
    logger.info(f"Added mail account {account.id}")
    return True


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
        from suzent.core.secrets import get_secret_manager

        get_secret_manager().set_backend_only(account.secret_key, password)
    accounts[account_id] = account.model_dump()
    _save(accounts)
    return account


def remove_account(account_id: str) -> bool:
    accounts = _load()
    if account_id not in accounts:
        return False
    from suzent.core.secrets import get_secret_manager

    get_secret_manager().delete(secret_key_for(account_id))
    del accounts[account_id]
    _save(accounts)
    logger.info(f"Removed mail account {account_id}")
    return True


def get_password(account: MailAccount) -> str | None:
    from suzent.core.secrets import get_secret_manager

    return get_secret_manager().get(account.secret_key)


def resolve_account(account_id: str | None) -> MailAccount:
    """The named account, or the only one when none is named.

    Raises LookupError with a message the agent can act on.
    """
    accounts = list_accounts()
    if not accounts:
        raise LookupError(
            "No mailbox is connected. Ask the user to add one in "
            "Settings → Email (sign-in uses an app password or authorization code)."
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
