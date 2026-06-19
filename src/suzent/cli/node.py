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
    """List everything this device is linked to: WS nodes, peers it drives, and
    devices that can drive it."""

    async def _run():
        try:
            client = get_client()
            nodes_data, peers_data, devices_data = await asyncio.gather(
                client.nodes.list(),
                client.nodes.peers(),
                client.nodes.devices(),
            )
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

        nodes = nodes_data.get("nodes", [])
        peers = peers_data.get("peers", [])
        devices = devices_data.get("devices", [])
        # Devices that can drive us but aren't also peers we drive (dedupe by name).
        peer_names = {p.get("name", "").lower() for p in peers}
        inbound = [
            d for d in devices if d.get("display_name", "").lower() not in peer_names
        ]

        if not (nodes or peers or inbound):
            typer.echo("No nodes or linked devices.")
            return

        typer.echo("📡 Nodes & devices\n")
        for n in nodes:
            dot = "🟢" if n.get("status") == "connected" else "⚪"
            caps = ", ".join(c["name"] for c in n.get("capabilities", [])) or "none"
            typer.echo(f"  {dot} {n['display_name']} ({n['platform']})")
            typer.echo(f"     node · {caps}")
        for p in peers:
            dot = "🟢" if p.get("online") else "⚪"
            direction = {
                "one_way": "you drive it",
                "mutual": "mutual",
                "paused": "paused",
            }.get(p.get("mode", "one_way"), p.get("mode"))
            typer.echo(f"  {dot} {p['name']}")
            typer.echo(f"     peer · {direction} · {p['base_url']}")
        for d in inbound:
            dot = "🟢" if d.get("connected") else "⚪"
            scope = d.get("scope", "agent")
            typer.echo(f"  {dot} {d['display_name']} ({d.get('platform', 'unknown')})")
            typer.echo(f"     device · can control this device ({scope})")
        typer.echo("")

    asyncio.run(_run())


@node_app.command("trigger")
def node_trigger(
    peer: str = typer.Argument(help="Peer id or name from `suzent node list`"),
    prompt: str = typer.Argument(help="Prompt to run on the peer's agent"),
    chat_id: Optional[str] = typer.Option(None, "--chat-id", help="Reuse a chat"),
):
    """Run a prompt on a peer device's agent and stream the reply."""
    import json as _json

    async def _run():
        try:
            client = get_client()
            data = await client.nodes.peers()
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

        peers = data.get("peers", [])
        match = next(
            (
                p
                for p in peers
                if p["peer_id"] == peer or p.get("name", "").lower() == peer.lower()
            ),
            None,
        )
        if not match:
            typer.echo(f"❌ No peer '{peer}'. See `suzent node list`.")
            raise typer.Exit(code=1)

        typer.echo(f"⚡ {match['name']}: ")
        try:
            async for chunk in client.nodes.trigger(match["peer_id"], prompt, chat_id):
                for line in chunk.decode("utf-8", "replace").splitlines():
                    if not line.startswith("data: "):
                        continue
                    body = line[6:].strip()
                    if body == "[DONE]":
                        continue
                    try:
                        event = _json.loads(body)
                    except _json.JSONDecodeError:
                        continue
                    if event.get("type") == "TEXT_MESSAGE_CONTENT":
                        typer.echo(event.get("delta", ""), nl=False)
                    elif event.get("type") in ("error", "RUN_ERROR"):
                        typer.echo(f"\n❌ {event.get('data') or event.get('message')}")
            typer.echo("")
        except ClientError as e:
            typer.echo(f"\n❌ {e}")
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
        client = get_client()
        try:
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
            # `invoke` targets WS nodes. If the target is a control-grant peer,
            # transparently proxy the capability to that peer.
            if "not found" in str(e).lower():
                try:
                    peers = (await client.nodes.peers()).get("peers", [])
                except ClientError:
                    peers = []
                match = next(
                    (
                        p
                        for p in peers
                        if p["peer_id"] == node
                        or p.get("name", "").lower() == node.lower()
                    ),
                    None,
                )
                if match:
                    try:
                        result = await client.nodes.invoke_peer(
                            match["peer_id"], command, parsed_params, timeout=timeout
                        )
                    except ClientError as pe:
                        typer.echo(f"❌ Couldn't reach peer '{match['name']}': {pe}")
                        raise typer.Exit(code=1)
                    if result.get("error"):
                        typer.echo(f"❌ Failed on peer: {result['error']}")
                        raise typer.Exit(code=1)
                    payload = result.get("result", result)
                    typer.echo(f"✅ Result: {json.dumps(payload, indent=2)}")
                    return
                # Neither a node nor a known peer on this device.
                typer.echo(
                    f"❌ No node or peer matching '{node}' on this device.\n"
                    f"   Run `suzent nodes list` and invoke by NAME — peer ids "
                    f"differ per device. To invoke back, the link must be Mutual."
                )
                raise typer.Exit(code=1)
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


@node_app.command("discover")
def node_discover(
    timeout: float = typer.Option(2.0, "--timeout", "-t", help="LAN browse seconds"),
):
    """Discover Suzent peers on the local network (mDNS) and tailnet."""

    async def _run():
        try:
            client = get_client()
            data = await client.nodes.discover(timeout=timeout)
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

        def _show(group, items):
            typer.echo(f"\n{group} ({len(items)}):")
            if not items:
                typer.echo("  (none)")
                return
            for it in items:
                reach = it.get("reachable")
                dot = "🟢" if reach else ("⚪" if reach is False else "  ")
                typer.echo(f"  {dot} {it['name']} — {it['gateway_url']}")

        _show("📡 LAN (mDNS)", data.get("lan", []))
        _show("🔒 Tailscale", data.get("tailscale", []))
        typer.echo("\nConnect with: suzent node connect <gateway_url>")

    asyncio.run(_run())


@node_app.command("connect")
def node_connect(
    gateway_url: str = typer.Argument(help="ws://host:port/ws/node of the remote"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="This node's name"),
    token: Optional[str] = typer.Option(
        None, "--token", help="Shared secret (token mode)"
    ),
):
    """Join a remote Suzent as a node (outbound). Approve on the remote if needed."""

    async def _run():
        try:
            client = get_client()
            result = await client.nodes.connect(
                gateway_url, name=name or "", token=token or ""
            )
            typer.echo(
                f"🔗 Connecting to {gateway_url} as '{result.get('display_name')}' "
                f"(status: {result.get('status')})."
            )
            typer.echo("Check `suzent node connections` for the pairing code/status.")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("connections")
def node_connections():
    """List outbound connections this device has initiated."""

    async def _run():
        try:
            client = get_client()
            data = await client.nodes.connections()
            conns = data.get("connections", [])
            if not conns:
                typer.echo("No outbound connections.")
                return
            typer.echo(f"🔗 Outbound connections ({len(conns)}):\n")
            for c in conns:
                line = f"  • {c['gateway_url']} — {c['status']}"
                if c.get("pairing_code"):
                    line += f" (approve code {c['pairing_code']} on the remote)"
                if c.get("error"):
                    line += f" — {c['error']}"
                typer.echo(line)
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@node_app.command("disconnect")
def node_disconnect(
    gateway_url: str = typer.Argument(help="ws://host:port/ws/node to disconnect"),
):
    """Stop an outbound connection."""

    async def _run():
        try:
            client = get_client()
            result = await client.nodes.disconnect(gateway_url)
            if result.get("success"):
                typer.echo(f"🔌 Disconnected from {gateway_url}.")
            else:
                typer.echo(f"❌ {result.get('message', 'Disconnect failed')}")
                raise typer.Exit(code=1)
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())
