"""Server presets for common mailbox providers.

Every preset signs in over IMAP/SMTP with the mailbox address and an
app-specific password (QQ and NetEase call it an authorization code, 授权码).
Providers that have switched off password sign-in are listed with
``oauth_only`` so the settings page can say so instead of failing at login.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

SmtpSecurity = Literal["ssl", "starttls"]


@dataclass(frozen=True)
class MailProvider:
    id: str
    label: str
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_security: SmtpSecurity = "ssl"
    # Gmail files SMTP-sent mail in Sent by itself; most others do not, so
    # Suzent appends a copy there unless the account turns it off.
    server_saves_sent: bool = False
    # NetEase rejects SELECT with "Unsafe Login" until the client sends the
    # RFC 2971 ID command.
    needs_imap_id: bool = False
    oauth_only: bool = False
    password_help_url: str = ""
    domains: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["domains"] = list(self.domains)
        return data


PROVIDERS: dict[str, MailProvider] = {
    p.id: p
    for p in (
        MailProvider(
            id="qq",
            label="QQ Mail",
            imap_host="imap.qq.com",
            smtp_host="smtp.qq.com",
            password_help_url="https://service.mail.qq.com/detail/0/75",
            domains=("qq.com", "foxmail.com", "vip.qq.com"),
        ),
        MailProvider(
            id="163",
            label="NetEase 163",
            imap_host="imap.163.com",
            smtp_host="smtp.163.com",
            needs_imap_id=True,
            password_help_url="https://help.mail.163.com/",
            domains=("163.com",),
        ),
        MailProvider(
            id="126",
            label="NetEase 126",
            imap_host="imap.126.com",
            smtp_host="smtp.126.com",
            needs_imap_id=True,
            password_help_url="https://help.mail.163.com/",
            domains=("126.com",),
        ),
        MailProvider(
            id="yeah",
            label="NetEase yeah.net",
            imap_host="imap.yeah.net",
            smtp_host="smtp.yeah.net",
            needs_imap_id=True,
            password_help_url="https://help.mail.163.com/",
            domains=("yeah.net",),
        ),
        MailProvider(
            id="gmail",
            label="Gmail",
            imap_host="imap.gmail.com",
            smtp_host="smtp.gmail.com",
            server_saves_sent=True,
            password_help_url="https://myaccount.google.com/apppasswords",
            domains=("gmail.com", "googlemail.com"),
        ),
        MailProvider(
            id="icloud",
            label="iCloud Mail",
            imap_host="imap.mail.me.com",
            smtp_host="smtp.mail.me.com",
            smtp_port=587,
            smtp_security="starttls",
            password_help_url="https://support.apple.com/102654",
            domains=("icloud.com", "me.com", "mac.com"),
        ),
        MailProvider(
            id="yahoo",
            label="Yahoo Mail",
            imap_host="imap.mail.yahoo.com",
            smtp_host="smtp.mail.yahoo.com",
            password_help_url="https://help.yahoo.com/kb/SLN15241.html",
            domains=("yahoo.com",),
        ),
        MailProvider(
            id="aliyun",
            label="Aliyun Mail",
            imap_host="imap.aliyun.com",
            smtp_host="smtp.aliyun.com",
            domains=("aliyun.com",),
        ),
        MailProvider(
            id="exmail",
            label="Tencent Exmail",
            imap_host="imap.exmail.qq.com",
            smtp_host="smtp.exmail.qq.com",
            password_help_url="https://open.work.weixin.qq.com/help2/pc/18624",
        ),
        MailProvider(
            id="outlook",
            label="Outlook / Hotmail / Microsoft 365",
            imap_host="outlook.office365.com",
            smtp_host="smtp-mail.outlook.com",
            smtp_port=587,
            smtp_security="starttls",
            server_saves_sent=True,
            oauth_only=True,
            domains=("outlook.com", "hotmail.com", "live.com", "msn.com"),
        ),
        MailProvider(id="custom", label="Other (IMAP/SMTP)"),
    )
}


def get_provider(provider_id: str) -> MailProvider | None:
    return PROVIDERS.get(provider_id)


def guess_provider(email: str) -> MailProvider | None:
    domain = email.rpartition("@")[2].lower()
    for provider in PROVIDERS.values():
        if domain in provider.domains:
            return provider
    return None
