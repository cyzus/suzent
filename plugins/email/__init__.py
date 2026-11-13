"""Email through the himalaya CLI: search, read, draft, and send when allowed."""

from suzent.plugins import PluginContext

from . import accounts, himalaya, routes, watch
from .tools import MailDraftTool, MailReadTool, MailSearchTool, MailSendTool


def register(ctx: PluginContext) -> None:
    himalaya.use_binary(ctx.binary("himalaya"))
    accounts.use_secrets(ctx.secrets)
    for tool in (MailSearchTool, MailReadTool, MailDraftTool, MailSendTool):
        ctx.register_tool(tool)
    ctx.register_route("providers", routes.list_providers)
    ctx.register_route("accounts", routes.list_accounts)
    ctx.register_route("accounts", routes.add_account, methods=("POST",))
    ctx.register_route("accounts/update", routes.update_account, methods=("POST",))
    ctx.register_route("accounts/test", routes.test_account, methods=("POST",))
    ctx.register_route("accounts/remove", routes.remove_account, methods=("POST",))
    ctx.register_watcher(
        "inbox",
        lambda: watch.check_inboxes(ctx),
        every_seconds=watch.CHECK_EVERY_SECONDS,
    )
