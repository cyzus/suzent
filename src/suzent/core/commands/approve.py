"""Tool approval commands — social surfaces only (/y, /n, /approve, /deny)."""

from suzent.core.commands.base import register_command, CommandContext

_APPROVE = {"/approve", "/y", "/yes", "/allow", "/ya"}
_DENY = {"/n", "/no", "/deny", "/reject", "/na"}
_REMEMBER = {"/ya", "/na"}


@register_command(
    ["/y", "/yes", "/allow", "/ya", "/approve", "/n", "/no", "/deny", "/reject", "/na"],
    description="Approve or deny a pending tool action",
    usage="/y [id]  or  /n [id]",
    surfaces=["social"],
)
async def handle_approval(ctx: CommandContext, cmd: str, args: list) -> str | None:
    """Resolve a pending tool approval. Only meaningful on social surfaces."""
    if not ctx.platform or not ctx.channel_manager:
        return None  # not applicable on frontend — fall through

    from suzent.core.social_brain import get_active_social_brain

    brain = get_active_social_brain()
    if not brain:
        return None

    approved = cmd in _APPROVE
    remember = cmd in _REMEMBER

    # Resolve social target/thread id from chat context (social-{platform}-{target_id}).
    # Using sender_id here breaks session lookup in group chats.
    target_id = ctx.sender_id or ""
    prefix = f"social-{ctx.platform}-"
    if ctx.chat_id.startswith(prefix):
        target_id = ctx.chat_id[len(prefix) :]

    await brain.handle_approval_response(
        ctx.platform,
        target_id,
        approved,
        sender_id=ctx.sender_id,
        remember=remember,
    )
    return ""  # handled, no reply text needed (brain sends its own response)
