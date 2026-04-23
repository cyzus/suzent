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
            result = await client.nodes.invoke(node, command, parsed_params)

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
):
    """Start a local node host (speaker, camera) in the foreground."""
    from suzent.nodes.node_host import NodeHost, DEFAULT_GATEWAY_URL

    gateway_url = url or DEFAULT_GATEWAY_URL
    caps = capabilities.split(",") if capabilities else None
    host = NodeHost(gateway_url=gateway_url, display_name=name, capabilities=caps)

    typer.echo(f"🖥️  Starting node host '{name}'...")
    typer.echo(f"   Gateway: {url}")
    typer.echo(f"   Capabilities: {capabilities or 'all'}")
    typer.echo("   Press Ctrl+C to stop.\n")

    try:
        asyncio.run(host.run())
    except KeyboardInterrupt:
        typer.echo("\n🛑 Node host stopped.")
