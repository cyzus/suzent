import typer
from suzent.core.commands.base import register_command


@register_command(
    ["/node"],
    description="Manage companion devices and nodes",
    usage="/node <list|wake> [id]",
    surfaces=["cli", "frontend"],
    category="tools",
    options={"list": "List all connected nodes", "wake": "Wake up a specific node"},
)
def handle_node(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="Subcommand: list, wake"),
    node_id: str = typer.Argument(None, help="The ID of the node to wake"),
):
    async def _impl():
        from suzent.cli._http import get_server_url
        import httpx

        action_lower = action.lower()
        base_url = get_server_url()

        if action_lower == "list":
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.get(f"{base_url}/nodes", timeout=5.0)
                    if res.status_code != 200:
                        return f"❌ Server returned {res.status_code}"
                    data = res.json()

                nodes = data.get("nodes", [])
                if not nodes:
                    return "📱 **Connected Nodes:**\n  None currently registered."

                lines = [f"📱 **Connected Nodes ({len(nodes)}):**"]
                for n in nodes:
                    status = "🟢" if n.get("status") == "connected" else "🔴"
                    lines.append(
                        f"  {status} **{n['display_name']}** ({n['platform']})  `{n['node_id']}`"
                    )

                return "\n".join(lines)
            except Exception as e:
                return f"❌ Error retrieving nodes: {e}"

        elif action_lower == "wake":
            if not node_id:
                return "Usage error: Missing node_id. Example: /node wake my-phone"

            try:
                async with httpx.AsyncClient() as client:
                    # Invoke generic wake command (assuming system.wake is handled by node)
                    res = await client.post(
                        f"{base_url}/nodes/{node_id}/invoke",
                        json={"command": "system.wake", "params": {}},
                        timeout=10.0,
                    )
                    if res.status_code == 404:
                        return f"❌ Node not found: '{node_id}'"

                    res.raise_for_status()
                    data = res.json()

                if data.get("success"):
                    return f"✅ Successfully woke up node '{node_id}'."
                else:
                    err = data.get("error", "Unknown error")
                    return f"❌ Failed to wake node '{node_id}': {err}"
            except httpx.ConnectError:
                return "❌ Cannot connect to Suzent server to wake the node."
            except Exception as e:
                return f"❌ Command error: {e}"

        else:
            return f"Unknown node action '{action}'. Usage: /node <list|wake> [id]"

    return _impl
