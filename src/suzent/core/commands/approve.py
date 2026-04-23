import typer
from suzent.core.commands.base import register_command, CommandContext

_APPROVE = {"/approve", "/y", "/yes", "/allow", "/ya"}
_DENY = {"/n", "/no", "/deny", "/reject", "/na"}
_REMEMBER = {"/ya", "/na"}


@register_command(
    ["/approve", "/y", "/yes", "/allow", "/ya"],
    description="Approve a pending tool action",
    usage="/approve [id]",
    surfaces=["social"],
    category="tools",
    hidden=True,
)
def handle_approve(ctx: typer.Context, req_id: str = typer.Argument(None)):
    """Approve a pending tool action."""

    async def _impl():
        return await _resolve_approval(ctx, True, req_id)

    return _impl


@register_command(
    ["/deny", "/n", "/no", "/reject", "/na"],
    description="Deny a pending tool action",
    usage="/deny [id]",
    surfaces=["social"],
    category="tools",
    hidden=True,
)
def handle_deny(ctx: typer.Context, req_id: str = typer.Argument(None)):
    """Deny a pending tool action."""

    async def _impl():
        return await _resolve_approval(ctx, False, req_id)

    return _impl


async def _resolve_approval(ctx: typer.Context, approved: bool, req_id: str):
    cmd_ctx: CommandContext = ctx.obj
    if not cmd_ctx.platform or not cmd_ctx.channel_manager:
        return None  # not applicable on frontend — fall through

    from suzent.core.social_brain import get_active_social_brain

    brain = get_active_social_brain()
    if not brain:
        return None

    cmd_name = "/" + ctx.info_name
    remember = cmd_name in _REMEMBER

    target_id = cmd_ctx.sender_id or ""
    prefix = f"social-{cmd_ctx.platform}-"
    if cmd_ctx.chat_id.startswith(prefix):
        target_id = cmd_ctx.chat_id[len(prefix) :]

    await brain.handle_approval_response(
        cmd_ctx.platform,
        target_id,
        approved,
        sender_id=cmd_ctx.sender_id,
        remember=remember,
    )
    return ""
