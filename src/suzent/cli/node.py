"""
CLI subcommands for managing connected nodes.

Usage:
    suzent nodes list
    suzent nodes status
    suzent nodes describe <node>
    suzent nodes invoke <node> <command> [--params JSON]
    suzent nodes host [--name NAME] [--capabilities CAPS]
"""

import json
import asyncio
from typing import Optional

import typer
from suzent.client import get_client
from suzent.client.base import ClientError
from suzent.cli.utils import infer_type

node_app = typer.Typer(help="Manage connected nodes (companion devices)")


@node_app.command("list")
def node_list():
    """List all connected nodes."""

    async def _run():
        try:
            client = get_client()
            data = await client.nodes.list()
            nodes = data.get("nodes", [])

            if not nodes:
                typer.echo("No nodes connected.")
                return

            typer.echo(f"📡 Connected nodes ({len(nodes)}):\n")
            for node in nodes:
                status_icon = "🟢" if node.get("status") == "connected" else "🔴"
                caps = node.get("capabilities", [])
                cap_names = ", ".join(c["name"] for c in caps) if caps else "none"
                typer.echo(
                    f"  {status_icon} {node['display_name']} ({node['platform']})\n"
                    f"     ID: {node['node_id']}\n"
                    f"     Capabilities: {cap_names}\n"
                )
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("status")
def node_status():
    """Show node system connectivity summary."""

    async def _run():
        try:
            client = get_client()
            data = await client.nodes.list()
            nodes = data.get("nodes", [])
            connected = sum(1 for n in nodes if n.get("status") == "connected")
            total = len(nodes)

            typer.echo(f"📡 Nodes: {connected}/{total} connected")
            for node in nodes:
                status_icon = "🟢" if node.get("status") == "connected" else "🔴"
                typer.echo(
                    f"  {status_icon} {node['display_name']} ({node['platform']})"
                )
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("describe")
def node_describe(
    node: str = typer.Argument(help="Node ID or display name"),
):
    """Show detailed info about a specific node."""

    async def _run():
        try:
            client = get_client()
            data = await client.nodes.describe(node)

            if "error" in data:
                typer.echo(f"❌ {data['error']}")
                raise typer.Exit(code=1)

            typer.echo(f"📡 Node: {data['display_name']}")
            typer.echo(f"   ID: {data['node_id']}")
            typer.echo(f"   Platform: {data['platform']}")
            typer.echo(f"   Status: {data['status']}")
            typer.echo(f"   Connected: {data.get('connected_at', 'unknown')}")

            caps = data.get("capabilities", [])
            if caps:
                typer.echo(f"\n   Capabilities ({len(caps)}):")
                for cap in caps:
                    desc = f" — {cap['description']}" if cap.get("description") else ""
                    typer.echo(f"     • {cap['name']}{desc}")
                    if cap.get("params_schema"):
                        for param, ptype in cap["params_schema"].items():
                            typer.echo(f"       {param}: {ptype}")
            else:
                typer.echo("\n   No capabilities advertised.")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("invoke")
def node_invoke(
    node: str = typer.Argument(help="Node ID or display name"),
    command: str = typer.Argument(help="Command to invoke (e.g., camera.snap)"),
    params: Optional[str] = typer.Option(
        None, "--params", "-p", help='JSON params (e.g., \'{"format":"png"}\')'
    ),
    timeout: Optional[float] = typer.Option(
        None,
        "--timeout",
        "-t",
        help="Seconds to wait on the node's response (e.g. agent.run is slow)",
    ),
    extra_args: list[str] = typer.Argument(
        None, help="Key=value params (e.g. text=hello)"
    ),
):
    """
    Invoke a command on a connected node.

    You can pass parameters as JSON via --params, or as simple key=value pairs.
    Key-value pairs support basic type inference (int, float, bool, json).

    Examples:
        suzent node invoke "Local PC" speaker.speak text="Hello world"
        suzent node invoke "Local PC" speaker.speak text="Hi" prompt="cheerful"
        suzent node invoke "Local PC" camera.snap format=png
    """

    async def _run():
        parsed_params = {}
        if params:
            try:
                parsed_params = json.loads(params)
            except json.JSONDecodeError as e:
                typer.echo(f"❌ Invalid JSON params: {e}")
                raise typer.Exit(code=1)

        if extra_args:
            for arg in extra_args:
                if "=" not in arg:
                    parsed_params[arg] = True
                    continue

                key, value_str = arg.split("=", 1)
                parsed_params[key] = infer_type(value_str)

        typer.echo(f"⚡ Invoking '{command}' on node '{node}'...")
        try:
            client = get_client()
            result = await client.nodes.invoke(
                node, command, parsed_params, timeout=timeout
            )

            if result.get("success"):
                typer.echo(f"✅ Result: {json.dumps(result.get('result'), indent=2)}")
            else:
                error = result.get("error", "Unknown error")
                typer.echo(f"❌ Failed: {error}")
                raise typer.Exit(code=1)
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("host")
def node_host(
    name: str = typer.Option(
        "Local PC", "--name", "-n", help="Display name for this node"
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url",
        help="Gateway WebSocket URL (default uses SUZENT_PORT env or 25314)",
    ),
    capabilities: Optional[str] = typer.Option(
        None,
        "--capabilities",
        "-c",
        help="Comma-separated capability filter (default: all)",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        help="Shared secret for the server's 'token' auth mode "
        "(or set SUZENT_NODE_TOKEN)",
    ),
    server_url: Optional[str] = typer.Option(
        None,
        "--server-url",
        help="HTTP base URL of the local agent for agent.run "
        "(default: derived from --url)",
    ),
):
    """Start a local node host (speaker, camera, agent.run) in the foreground."""
    import os

    from suzent.nodes.node_host import NodeHost, DEFAULT_GATEWAY_URL

    gateway_url = url or DEFAULT_GATEWAY_URL
    caps = capabilities.split(",") if capabilities else None
    auth_token = token if token is not None else os.environ.get("SUZENT_NODE_TOKEN", "")
    host = NodeHost(
        gateway_url=gateway_url,
        display_name=name,
        capabilities=caps,
        auth_token=auth_token,
        server_url=server_url,
    )

    typer.echo(f"🖥️  Starting node host '{name}'...")
    typer.echo(f"   Gateway: {gateway_url}")
    typer.echo(f"   Capabilities: {capabilities or 'all'}")
    typer.echo("   Press Ctrl+C to stop.\n")

    try:
        asyncio.run(host.run())
    except KeyboardInterrupt:
        typer.echo("\n🛑 Node host stopped.")


@node_app.command("pending")
def node_pending():
    """List node connections awaiting operator approval (approve mode)."""

    async def _run():
        try:
            client = get_client()
            data = await client.nodes.pending()
            pending = data.get("pending", [])
            if not pending:
                typer.echo("No nodes awaiting approval.")
                return
            typer.echo(f"⏳ Pending approval ({len(pending)}):\n")
            for p in pending:
                caps = ", ".join(c["name"] for c in p.get("capabilities", [])) or "none"
                typer.echo(
                    f"  • {p['display_name']} ({p['platform']})\n"
                    f"     Code: {p['pairing_code']}\n"
                    f"     Capabilities: {caps}\n"
                    f"     Requested: {p.get('requested_at', 'unknown')}\n"
                )
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("approve")
def node_approve(
    code: str = typer.Argument(help="Pairing code from `suzent node pending`"),
):
    """Approve a pending node connection (mints a durable device token)."""

    async def _run():
        try:
            client = get_client()
            result = await client.nodes.approve(code)
            if result.get("success"):
                typer.echo(f"✅ Approved {code}.")
            else:
                typer.echo(f"❌ {result.get('message', 'Approval failed')}")
                raise typer.Exit(code=1)
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("deny")
def node_deny(
    code: str = typer.Argument(help="Pairing code from `suzent node pending`"),
):
    """Deny a pending node connection."""

    async def _run():
        try:
            client = get_client()
            result = await client.nodes.deny(code)
            if result.get("success"):
                typer.echo(f"🚫 Denied {code}.")
            else:
                typer.echo(f"❌ {result.get('message', 'Deny failed')}")
                raise typer.Exit(code=1)
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("devices")
def node_devices():
    """List durably-approved devices (per-device tokens)."""

    async def _run():
        try:
            client = get_client()
            data = await client.nodes.devices()
            devices = data.get("devices", [])
            if not devices:
                typer.echo("No approved devices.")
                return
            typer.echo(f"🔐 Approved devices ({len(devices)}):\n")
            for d in devices:
                dot = "🟢" if d.get("connected") else "⚪"
                typer.echo(
                    f"  {dot} {d['display_name']} ({d['platform']})\n"
                    f"     Device ID: {d['device_id']}\n"
                    f"     Approved: {d.get('approved_at', 'unknown')}\n"
                )
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("revoke")
def node_revoke(
    device_id: str = typer.Argument(help="Device ID from `suzent node devices`"),
):
    """Revoke a device's durable token (it must re-pair to reconnect)."""

    async def _run():
        try:
            client = get_client()
            result = await client.nodes.revoke(device_id)
            if result.get("success"):
                typer.echo(f"🗑️  Revoked device {device_id}.")
            else:
                typer.echo(f"❌ {result.get('message', 'Revoke failed')}")
                raise typer.Exit(code=1)
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())
