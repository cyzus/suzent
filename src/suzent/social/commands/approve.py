"""Approval command handler."""

from suzent.core import approval_manager
from suzent.social.commands.base import register_command


@register_command(["/approve", "/y", "/yes", "/allow", "/n", "/no", "/deny", "/reject"])
async def handle_approval(message, channel_manager, args):
    """Handle tool approval resolution with friendly UX."""
    content = message.content.strip().lower()
    approved = not any(content.startswith(p) for p in ["/n", "/no", "/deny", "/reject"])

    request_id = args[0] if args else None

    # If no ID provided, try to auto-resolve if there's exactly one pending approval globally
    if not request_id:
        pending = approval_manager.get_all_pending_approvals()
        if len(pending) == 1:
            request_id = pending[0]["request_id"]
        elif len(pending) > 1:
            await channel_manager.send_message(
                message.platform,
                message.sender_id,
                "⚠️ Multiple approvals pending. Please specify the ID (e.g., `/y 123`).",
            )
            return True
        else:
            await channel_manager.send_message(
                message.platform, message.sender_id, "⚠️ No pending approvals."
            )
            return True

    # Resolve globally
    if approval_manager.resolve_approval(request_id, approved):
        status = "✅ Approved" if approved else "⛔ Denied"
        await channel_manager.send_message(
            message.platform, message.sender_id, f"{status} action `{request_id}`"
        )
    else:
        await channel_manager.send_message(
            message.platform,
            message.sender_id,
            f"⚠️ Could not find pending approval for `{request_id}`.",
        )
    return True
