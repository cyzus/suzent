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
from typing import Optional

import typer

from suzent.cli._http import _http_get, _http_post

nodes_app = typer.Typer(help="Manage connected nodes (companion devices)")


def _infer_type(value_str: str):
    """Infer a Python type from a CLI string value."""
    lower = value_str.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in ("null", "none"):
        return None

    for converter in (int, float):
        try:
            return converter(value_str)
        except ValueError:
            pass

    if value_str.startswith(("{", "[")):
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            pass

    return value_str


@nodes_app.command("list")
def nodes_list():
    """List all connected nodes."""
    data = _http_get("/nodes")
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


@nodes_app.command("status")
def nodes_status():
    """Show node system connectivity summary."""
    data = _http_get("/nodes")
    nodes = data.get("nodes", [])
    connected = sum(1 for n in nodes if n.get("status") == "connected")
    total = len(nodes)

    typer.echo(f"📡 Nodes: {connected}/{total} connected")
    for node in nodes:
        status_icon = "🟢" if node.get("status") == "connected" else "🔴"
        typer.echo(f"  {status_icon} {node['display_name']} ({node['platform']})")


@nodes_app.command("describe")
def nodes_describe(
    node: str = typer.Argument(help="Node ID or display name"),
):
    """Show detailed info about a specific node."""
    data = _http_get(f"/nodes/{node}")

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


@nodes_app.command("invoke")
def nodes_invoke(
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
        suzent nodes invoke "Local PC" speaker.speak text="Hello world"
        suzent nodes invoke "Local PC" speaker.speak text="Hi" prompt="cheerful"
        suzent nodes invoke "Local PC" camera.snap format=png
    """
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
            parsed_params[key] = _infer_type(value_str)

    typer.echo(f"⚡ Invoking '{command}' on node '{node}'...")
    result = _http_post(
        f"/nodes/{node}/invoke",
        data={"command": command, "params": parsed_params},
    )

    if result.get("success"):
        typer.echo(f"✅ Result: {json.dumps(result.get('result'), indent=2)}")
    else:
        error = result.get("error", "Unknown error")
        typer.echo(f"❌ Failed: {error}")
        raise typer.Exit(code=1)


@nodes_app.command("host")
def nodes_host(
    name: str = typer.Option(
        "Local PC", "--name", "-n", help="Display name for this node"
    ),
    url: str = typer.Option(
        "ws://localhost:25314/ws/node", "--url", help="Gateway WebSocket URL"
    ),
    capabilities: Optional[str] = typer.Option(
        None,
        "--capabilities",
        "-c",
        help="Comma-separated capability filter (default: all)",
    ),
):
    """Start a local node host (speaker, camera) in the foreground."""
    import asyncio

    from suzent.nodes.node_host import NodeHost

    caps = capabilities.split(",") if capabilities else None
    host = NodeHost(gateway_url=url, display_name=name, capabilities=caps)

    typer.echo(f"🖥️  Starting node host '{name}'...")
    typer.echo(f"   Gateway: {url}")
    typer.echo(f"   Capabilities: {capabilities or 'all'}")
    typer.echo("   Press Ctrl+C to stop.\n")

    try:
        asyncio.run(host.run())
    except KeyboardInterrupt:
        typer.echo("\n🛑 Node host stopped.")
