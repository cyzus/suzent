import typer
from suzent.core.commands.base import register_command


@register_command(
    ["/node"],
    description="Manage companion devices and nodes",
    usage="/node <list|invoke> [id]",
    surfaces=["cli", "frontend"],
    category="tools",
    options={
        "list": "List all connected nodes",
        "status": "Check node connectivity status",
        "describe": "Show detailed capabilities of a node",
        "invoke": "Invoke a command on a specific node",
    },
)
def handle_node(
    ctx: str,
    action: str = typer.Argument(..., help="Subcommand: list, invoke"),
    node_id: str = typer.Argument(None, help="Node ID info"),
):
    async def _impl():
        from suzent.client import get_client
        from suzent.client.base import ClientError

        action_lower = action.lower()

        if action_lower == "list":
            try:
                client = get_client()
                data = await client.nodes.list()

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
            except ClientError as e:
                return f"❌ Error retrieving nodes: {e}"

        elif action_lower == "status":
            try:
                client = get_client()
                data = await client.nodes.list()
                nodes = data.get("nodes", [])
                connected = sum(1 for n in nodes if n.get("status") == "connected")

                lines = [f"📡 Nodes: {connected}/{len(nodes)} connected"]
                for n in nodes:
                    status = "🟢" if n.get("status") == "connected" else "🔴"
                    lines.append(
                        f"  {status} **{n['display_name']}** ({n['platform']})"
                    )
                return "\n".join(lines)
            except ClientError as e:
                return f"❌ {e}"

        elif action_lower == "describe":
            if not ctx:
                return "Usage error: Missing node_id. Example: /node describe my-phone"
            node_id_arg = ctx.split(" ", 1)[0]
            try:
                client = get_client()
                data = await client.nodes.describe(node_id_arg)
                if "error" in data:
                    return f"❌ {data['error']}"

                lines = [f"📡 **Node: {data['display_name']}**"]
                lines.append(f"   ID: `{data['node_id']}`")
                lines.append(f"   Platform: {data['platform']}")
                lines.append(f"   Status: {data['status']}")

                caps = data.get("capabilities", [])
                if caps:
                    lines.append(f"\n   **Capabilities ({len(caps)}):**")
                    for cap in caps:
                        lines.append(
                            f"     • `{cap['name']}` — {cap.get('description', '')}"
                        )
                return "\n".join(lines)
            except ClientError as e:
                return f"❌ {e}"

        elif action_lower == "invoke":
            parts = ctx.split(" ", 1)
            if not parts or not parts[0]:
                return "Usage error: Missing node_id. Example: /node invoke my-phone system.wake"
            node_id_arg = parts[0]

            command_arg = "system.wake"
            params_dict = {}
            if len(parts) > 1:
                cmd_parts = parts[1].split(" ", 1)
                command_arg = cmd_parts[0]
                if len(cmd_parts) > 1:
                    # simplistic pass-through of rest as string or dict
                    import json

                    try:
                        params_dict = json.loads(cmd_parts[1])
                    except Exception:
                        params_dict = {"raw": cmd_parts[1]}

            try:
                client = get_client()
                data = await client.nodes.invoke(node_id_arg, command_arg, params_dict)

                if data.get("success"):
                    res = data.get("result")
                    return (
                        f"✅ '{command_arg}' invoked on '{node_id_arg}'.\nResult: {res}"
                    )
                else:
                    err = data.get("error", "Unknown error")
                    return f"❌ Failed to invoke '{command_arg}' on node '{node_id_arg}': {err}"
            except ClientError as e:
                return f"❌ Command error: {e}"

        else:
            return f"Unknown node action '{action}'. Usage: /node <list|status|describe|invoke>"

    return _impl
