import typer

from suzent.core.commands.base import CommandContext, register_command


@register_command(
    ["/undo"],
    description="Undo file changes from the most recent agent turn",
    usage="/undo",
    category="tools",
)
def handle_undo(ctx: typer.Context):
    async def _impl() -> str:
        from suzent.core.file_tracker import (
            FileRestoreConflictError,
            FileTracker,
        )
        from suzent.core.retry import load_retry_checkpoint

        cmd_ctx: CommandContext = ctx.obj
        checkpoint = load_retry_checkpoint(cmd_ctx.chat_id)
        if checkpoint is None or not getattr(checkpoint, "file_snapshot", None):
            return "ℹ No file changes are available to undo."

        snapshot = FileTracker.snapshot_from_json(checkpoint.file_snapshot)
        try:
            changed = FileTracker.apply_snapshot(cmd_ctx.chat_id, snapshot)
        except FileRestoreConflictError as exc:
            paths = "\n".join(f"- {path}" for path in exc.paths)
            return (
                "⚠ Undo cancelled because these files were modified after the "
                f"agent turn:\n{paths}"
            )

        if not changed:
            return "ℹ Files already match the pre-turn state."
        return f"✓ Undid the previous turn's changes in {len(changed)} file(s)."

    return _impl
